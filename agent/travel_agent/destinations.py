"""Resolve destinations against Ostrovok's public autocomplete, not a whitelist."""

import asyncio
from collections import OrderedDict
import re
import time

import httpx

from .tools import ToolError

ENDPOINT = "https://ostrovok.ru/api/site/multicomplete.json"
_cache = OrderedDict()
REGION_TYPES = {"City", "Province (State)", "Country", "Multi-Region (within a country)", "Multi-Region (across countries)", "Neighborhood", "Island"}
ALIASES = {"питер": "Санкт-Петербург", "спб": "Санкт-Петербург", "петербург": "Санкт-Петербург"}


class DestinationUnavailable(ToolError):
    def __init__(self, name, resolution):
        super().__init__(name)
        self.name, self.resolution = name, resolution


def normalized(value):
    return " ".join(value.casefold().replace("ё", "е").split())


def valid_slug(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9_-]+/(?:p/)?[a-z0-9_.-]+", value)) and ".." not in value


def comparable(value):
    return re.sub(r"^республика\s+|\s+республика$", "", normalized(value))


async def resolve_destination(name, country=None):
    # The user supplies a search term, never a URL or a catalogue path.
    if not isinstance(name, str) or not re.fullmatch(r"[\w\s.,()'’–—-]{1,160}", name) or not any(c.isalpha() for c in name):
        raise ToolError("Укажите название города или региона, а не ссылку.")
    query = ALIASES.get(normalized(name), name.strip())
    key = (normalized(query), normalized(country or ""))
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < cached[1]:
        _cache.move_to_end(key)
        return cached[2]
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.get(ENDPOINT, params={"query": query, "language": "ru"})
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("regions"), list):
            raise ValueError("missing regions")
        regions = []
        for item in data["regions"]:
            if not isinstance(item, dict):
                raise ValueError("invalid region")
            if item.get("type") not in REGION_TYPES:
                continue
            if not (type(item.get("id")) is int and isinstance(item.get("name"), str)
                    and valid_slug(item.get("slug")) and type(item.get("is_sales_closed")) is bool):
                raise ValueError("invalid destination metadata")
            if country and normalized(country) not in {normalized(item.get(k, "")) for k in ("country", "country_code", "country_en")}:
                continue
            regions.append({k: item.get(k) for k in ("id", "name", "type", "country", "country_code", "slug", "is_sales_closed", "name_en")})
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ToolError("Не удалось проверить направление в Островке. Это временная ошибка проверки, а не отсутствие отелей. Повторите запрос немного позже.") from exc
    exact = [r for r in regions if comparable(query) in {comparable(r["name"]), comparable(r.get("name_en") or "")}]
    matches = exact or [r for r in regions if comparable(query) == comparable(r["name"].split(",")[0])]
    selected = matches[0] if len(matches) == 1 else None
    status = ("closed" if selected["is_sales_closed"] else "available") if selected else "ambiguous" if regions else "not_found"
    result = dict(status=status, region=selected, suggestions=[r for r in regions if not r["is_sales_closed"]][:5])
    _cache[key] = (time.monotonic(), 3600 if status == "available" else 300, result)
    while len(_cache) > 512:
        _cache.popitem(last=False)
    return result


async def destination_question(name, resolution):
    suggestions = resolution["suggestions"][:3]
    if not suggestions:
        # Alternatives are checked with the provider too; never advertise a
        # closed or unverified destination as an available fallback.
        checked = await asyncio.gather(*(resolve_destination(city) for city in ("Сочи", "Казань", "Санкт-Петербург")), return_exceptions=True)
        suggestions = [r["region"] for r in checked if isinstance(r, dict) and r["status"] == "available"]
    status = resolution["status"]
    intro = (
        f"Островок сейчас не предлагает бронирование по направлению «{name}»: продажи закрыты. "
        if status == "closed" else
        f"В поиске Островка не нашлось города или региона «{name}». Проверьте название или выберите другое направление. "
        if status == "not_found" else
        f"Островок нашёл несколько похожих направлений для «{name}». Уточните город или регион. "
    )
    labels = [r["name"] + (f", {r['country']}" if r.get("country") else "") for r in suggestions]
    question = "Какое направление выбрать?"
    return intro + ("Можно посмотреть: " + "; ".join(labels) + ". " if labels else "") + "Остальные условия поездки сохранены. " + question, question, suggestions
