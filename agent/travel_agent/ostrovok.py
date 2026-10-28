"""Read public Ostrovok catalogue pages. No rates, availability or booking claims."""

import json
import asyncio
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, urlparse, urljoin

import httpx

from .tools import ToolError

# Slugs verified in the supplied Ostrovok homepage archive. Never fetch a user URL.
CITIES = {
    "сортавала": "sortavala",
    "карелия": "sortavala",
    "чемал": "altai_republic_chemal",
    "алтай": "altai_republic_chemal",
    "осташков": "ostashkov",
    "селигер": "ostashkov",
    "стамбул": "turkey/istanbul",
    "минск": "belarus/minsk",
    "париж": "france/paris",
    "рим": "italy/rome",
    "венеция": "italy/venice",
    "сочи": "sochi",
    "москва": "moscow",
    "санкт-петербург": "st._petersburg",
    "петербург": "st._petersburg",
    "питер": "st._petersburg",
    "спб": "st._petersburg",
    "казань": "kazan",
    "ярославль": "yaroslavl",
    "владимир": "vladimir",
    "адлер": "adler",
    "анапа": "anapa",
    "краснодар": "krasnodar",
    "калининград": "kaliningrad",
    "нижний новгород": "nizhniy_novgorod",
    "кисловодск": "kislovodsk",
    "геленджик": "gelendzhik",
    "мурманск": "murmansk",
}
AMENITIES = {
    "has_internet": "Wi-Fi",
    "has_pool": "Бассейн",
    "has_parking": "Парковка",
    "has_spa": "Спа",
    "has_fitness": "Фитнес",
    "has_pets": "С питомцами",
    "has_kids": "Для детей",
}
_cache = {}


class PageData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        self.active = tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__"

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def catalogue_path(slug):
    return slug if "/" in slug else "russia/" + slug


def search_url(slug, spec=None):
    url = f"https://ostrovok.ru/hotel/{catalogue_path(slug)}/"
    query = {"language": "ru"}
    if spec and spec.dates:
        query["dates"] = (
            spec.dates.start.strftime("%d.%m.%Y")
            + "-"
            + spec.dates.end.strftime("%d.%m.%Y")
        )
    if spec and spec.travellers.adults:
        # Unknown child ages cannot be represented accurately; ask on the site.
        if not spec.travellers.children:
            query["guests"] = str(spec.travellers.adults)
    return url + "?" + urlencode(query)


def parse_hotels(html, slug):
    parser = PageData()
    parser.feed(html)
    try:
        page = json.loads("".join(parser.parts))["props"]["pageProps"]
        if page["searchRegionData"]["catalogSlug"] != catalogue_path(slug):
            raise ValueError("wrong region")
        hotels = page["serpData"]["hotels"]
        output = []
        seen = set()
        for item in hotels:
            hid, mid = item["id"], str(item["masterId"])
            if (
                not re.fullmatch(r"[a-zA-Z0-9_-]+", hid)
                or not mid.isdigit()
                or hid in seen
            ):
                continue
            seen.add(hid)
            images = [
                i["tmpl"].replace("{size}", "640x400") for i in item.get("images", [])
            ]
            images = [
                u
                for u in images
                if urlparse(u).scheme == "https"
                and urlparse(u).hostname == "cdn.ostrovok.ru"
            ]
            if not images:
                continue
            amenities = item.get("amenities", [])
            rating = item.get("rating")
            distance = item.get("searchRegionCenterDistance")
            reference = item.get("datelessRate") or {}
            nightly = reference.get("amount")
            beaches = [
                b["distance"]
                for b in (item.get("nearestBeaches") or [])
                if isinstance(b.get("distance"), (int, float)) and b["distance"] >= 0
            ]
            output.append(
                dict(
                    reference_nightly_minor=round(nightly * 100)
                    if type(nightly) in (int, float)
                    and 0 < nightly < 1000000
                    and reference.get("currency") == "RUB"
                    else None,
                    property_kind=item.get("kind"),
                    amenity_codes=amenities,
                    stars=item.get("stars"),
                    beach_m=min(beaches) if beaches else None,
                    id=hid,
                    source_kind="public",
                    coordinates={
                        "lat": item.get("location", {}).get("latitude"),
                        "lng": item.get("location", {}).get("longitude"),
                    },
                    name=str(item["name"])[:500],
                    address=str(item.get("location", {}).get("address", ""))[:500],
                    image_url=images[0],
                    images=images[:3],
                    url=f"https://ostrovok.ru/hotel/{catalogue_path(slug)}/mid{mid}/{hid}/",
                    rating=rating
                    if isinstance(rating, (int, float)) and 0 <= rating <= 10
                    else None,
                    reviews=item.get("numReviews")
                    if isinstance(item.get("numReviews"), int)
                    and item["numReviews"] >= 0
                    else None,
                    distance_m=distance
                    if isinstance(distance, (int, float)) and distance >= 0
                    else None,
                    amenities=[
                        label for key, label in AMENITIES.items() if key in amenities
                    ],
                )
            )
        if not output:
            raise ValueError("no public hotel cards")
        return output
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolError(
            "Не удалось прочитать карточки Островка. Откройте обычный поиск или попробуйте позже."
        ) from exc


async def search_hotels(spec, _page=1):
    destination = (spec.destination or "").strip().casefold().replace("ё", "е")
    slug = CITIES.get(destination)
    if not slug:
        raise ToolError(
            "Это направление пока не подключено к поиску ИИ. Попробуйте Сочи, Москву, Санкт-Петербург, Казань, Ярославль или обычный поиск Островка."
        )
    cache_key = slug if _page == 1 else f"{slug}:{_page}"
    page_url = search_url(slug) + (f"&page={_page}" if _page > 1 else "")
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < 300:
        hotels, checked_at = cached[1:]
    else:
        try:
            async with httpx.AsyncClient(
                timeout=18,
                follow_redirects=False,
                trust_env=False,
                headers={
                    "User-Agent": "OPlan-Hackathon/1.0 (public hotel discovery)",
                    "Accept-Language": "ru-RU",
                },
            ) as client:
                url = page_url
                for attempt in range(3):
                    async with client.stream("GET", url) as response:
                        if response.is_redirect:
                            redirected = urljoin(
                                url, response.headers.get("location", "")
                            )
                            parsed = urlparse(redirected)
                            if (
                                parsed.scheme != "https"
                                or parsed.netloc != "ostrovok.ru"
                                or parsed.path.rstrip("/")
                                != f"/hotel/{catalogue_path(slug)}"
                            ):
                                raise ValueError("unexpected redirect")
                            url = redirected
                            continue
                        response.raise_for_status()
                        chunks, size = [], 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 4_000_000:
                                raise ValueError("page too large")
                            chunks.append(chunk)
                        break
                else:
                    raise ValueError("too many redirects")
            hotels = parse_hotels(b"".join(chunks).decode("utf-8"), slug)
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolError(
                "Островок сейчас не ответил на поиск. Повторите запрос или откройте поиск на сайте."
            ) from exc
        checked_at = datetime.now(timezone.utc).isoformat()
        _cache[cache_key] = (time.monotonic(), hotels, checked_at)
    # Return the whole fetched candidate set; selection happens independently.
    suffix = "?" + search_url(slug, spec).split("?", 1)[1]
    output = [
        dict(h, url=h["url"] + suffix, checked_at=checked_at, source_url=page_url)
        for h in hotels
    ]
    if _page == 1 and (
        spec.travel_setting in {"forest", "nature", "mountains"}
        or spec.excluded_hotel_ids
    ):
        # Verified public pagination; bounded to 60 candidates. A missing extra
        # page never invents data or discards already fetched results.
        pages = await asyncio.gather(
            search_hotels(spec, 2), search_hotels(spec, 3), return_exceptions=True
        )
        for page in pages:
            if isinstance(page, Exception):
                continue
            output.extend(page[0])
        output = list({h["id"]: h for h in output}.values())
    from .public_content import remember

    for h in output:
        h["destination"] = spec.destination
        remember(h)
    return output, search_url(slug, spec)
