from datetime import date, timedelta
from decimal import Decimal
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    AwareDatetime,
    model_validator,
)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


Text = Annotated[str, Field(min_length=1, max_length=500)]
Count = Annotated[StrictInt, Field(ge=0, le=20)]


class Money(Model):
    amount_minor: Annotated[StrictInt, Field(ge=0, le=10**12)]
    currency: Literal["RUB"] = "RUB"


class Dates(Model):
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class Travellers(Model):
    adults: Annotated[StrictInt, Field(ge=1, le=20)] | None = None
    children: list[Annotated[StrictInt, Field(ge=0, le=17)] | None] = Field(
        default_factory=list, max_length=10
    )


class Constraints(Model):
    no_connections: StrictBool = False
    no_night_travel: StrictBool = False
    no_night_flights: StrictBool = False
    free_cancellation: StrictBool = False
    pets: StrictBool = False
    other: list[Text] = Field(default_factory=list, max_length=20)


class HotelPreferences(Model):
    pool: StrictBool | None = None
    parking: StrictBool | None = None
    spa: StrictBool | None = None
    fitness: StrictBool | None = None
    breakfast: StrictBool | None = None
    max_center_m: Annotated[StrictInt, Field(ge=0, le=100000)] | None = None
    max_beach_m: Annotated[StrictInt, Field(ge=0, le=100000)] | None = None
    min_rating: Annotated[float, Field(ge=0, le=10)] | None = None
    min_stars: Annotated[StrictInt, Field(ge=0, le=5)] | None = None


class OwnedTransport(Model):
    arrival: AwareDatetime
    departure: AwareDatetime
    terminal: Literal["airport", "station"] = "station"
    paid_total_minor: Annotated[StrictInt, Field(ge=0, le=10**12)] | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.departure <= self.arrival:
            raise ValueError("return departure must follow arrival")
        return self


class TripSpec(Model):
    transfer_provider: Literal["estimate", "hotel"] = "estimate"
    transport_mode: Literal["auto", "flight", "train", "car"] = "auto"
    transport_owned: StrictBool = False
    owned_transport: OwnedTransport | None = None
    excluded_hotel_ids: list[Text] = Field(default_factory=list, max_length=100)
    keep_hotel: StrictBool = False
    locked_hotel_id: str | None = None
    include_transport: StrictBool = False
    trip_budget: Money | None = None
    hotel_budget: Money | None = None
    travel_setting: Literal["forest", "nature", "mountains", "sea", "city", "any"] = (
        "any"
    )
    hotel_preferences: HotelPreferences = Field(default_factory=HotelPreferences)
    stay_nights: Annotated[StrictInt, Field(ge=1, le=60)] | None = None
    budget_period: Literal["stay", "night"] = "stay"
    origin: Text | None = None
    destination: Text | None = None
    country: Text | None = None
    dates: Dates | None = None
    duration_days: Annotated[StrictInt, Field(ge=1, le=365)] | None = None
    travellers: Travellers = Field(default_factory=Travellers)
    budget: Money | None = None
    budget_scope: Literal["booking", "whole_trip", "hotel"] | None = None
    expense_reserve: Money | None = None
    hard_constraints: Constraints = Field(default_factory=Constraints)
    preferences: list[Text] = Field(default_factory=list, max_length=30)
    locked_component_ids: list[Text] = Field(default_factory=list, max_length=20)


class TravellersPatch(Model):
    adults: Annotated[StrictInt, Field(ge=1, le=20)] | None = None
    children: list[Annotated[StrictInt, Field(ge=0, le=17)] | None] | None = None


class ConstraintsPatch(Model):
    no_connections: StrictBool | None = None
    no_night_travel: StrictBool | None = None
    no_night_flights: StrictBool | None = None
    free_cancellation: StrictBool | None = None
    pets: StrictBool | None = None
    other: list[Text] | None = None


class TripPatch(Model):
    transfer_provider: Literal["estimate", "hotel"] | None = None
    transport_mode: Literal["auto", "flight", "train", "car"] | None = None
    transport_owned: StrictBool | None = None
    owned_transport: OwnedTransport | None = None
    keep_hotel: StrictBool | None = None
    include_transport: StrictBool | None = None
    travel_setting: (
        Literal["forest", "nature", "mountains", "sea", "city", "any"] | None
    ) = None
    hotel_preferences: HotelPreferences | None = None
    stay_nights: Annotated[StrictInt, Field(ge=1, le=60)] | None = None
    budget_period: Literal["stay", "night"] | None = None
    origin: Text | None = None
    destination: Text | None = None
    country: Text | None = None
    dates: Dates | None = None
    duration_days: Annotated[StrictInt, Field(ge=1, le=365)] | None = None
    travellers: TravellersPatch | None = None
    budget: Money | None = None
    budget_scope: Literal["booking", "whole_trip", "hotel"] | None = None
    expense_reserve: Money | None = None
    hard_constraints: ConstraintsPatch | None = None


class Intent(Model):
    remove_hotel_preferences: list[
        Literal[
            "pool",
            "parking",
            "spa",
            "fitness",
            "breakfast",
            "max_center_m",
            "max_beach_m",
            "min_rating",
            "min_stars",
        ]
    ] = Field(default_factory=list, max_length=9)
    hotel_reference: Annotated[StrictInt, Field(ge=1, le=3)] | None = None
    patch: TripPatch = Field(default_factory=TripPatch)
    # Exact user excerpts for every modified top-level field; checked before patching.
    evidence: dict[str, Text] = Field(default_factory=dict)
    shift_days: Annotated[StrictInt, Field(ge=-365, le=365)] | None = None
    optimization: Literal["cheaper"] | None = None
    add_preferences: list[Text] = Field(default_factory=list, max_length=20)
    remove_preferences: list[Text] = Field(default_factory=list, max_length=20)
    add_locks: list[Text] = Field(default_factory=list, max_length=20)
    remove_locks: list[Text] = Field(default_factory=list, max_length=20)
    questions: list[Text] = Field(default_factory=list, max_length=6)
    action: Literal[
        "search",
        "inspire",
        "change",
        "clarify",
        "explain",
        "replace_options",
        "restore_options",
        "reviews",
        "nearby",
    ] = "search"


def has_nightly_evidence(quote: str) -> bool:
    """Shared by validation and constrained generation; duration is not a nightly rate."""
    return bool(
        re.search(
            r"за\s+(?:одну\s+|1\s+)?ночь|за\s+сутки|в\s+сутки|в\s+день|/\s*(?:ночь|сутки)|кажд\w*\s+ночь|per\s+night",
            quote,
            re.IGNORECASE,
        )
    )


def has_calendar_reference(message: str) -> bool:
    """Gate calendar output; nights, a month or a budget alone cannot supply dates."""
    if re.search(
        r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b", message
    ):
        return True
    month = r"(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
    day = r"(?<!\d)(?:3[01]|[12]\d|0?[1-9])(?!\d)"
    ordinal = r"(?:перв|втор|треть|четв[её]рт|пят|шест|седьм|восьм|девят|десят|\w+надцат|двадцат|тридцат)\w*"
    return bool(
        re.search(rf"(?:{day}|{ordinal})\s+{month}\b|\b{month}\s+{day}", message, re.I)
        or (
            re.search(month, message, re.I)
            and re.search(rf"\bс\s+{day}\s*(?:по|до|[-–—])\s*{day}", message, re.I)
        )
    )


def explicit_ruble_amount(quote: str) -> int | None:
    """Independent check for one numeric rouble amount, not a language-model parser."""
    pattern = r"(?<![\w.,])(\d(?:[\d \u00a0]*\d)?(?:[.,]\d+)?)\s*(тыс(?:яч[а-я]*)?\.?|млн\.?|миллион[а-я]*|[kк](?![а-яa-z])|руб[а-я]*|₽)"
    matches = list(re.finditer(pattern, quote, re.IGNORECASE))
    if len(matches) != 1:
        return None
    number, unit = matches[0].groups()
    value = Decimal(number.replace(" ", "").replace("\u00a0", "").replace(",", "."))
    multiplier = (
        1000000
        if unit.lower().startswith(("млн", "миллион"))
        else 1000
        if unit.lower().startswith("тыс") or unit.lower() in {"к", "k"}
        else 1
    )
    amount = value * multiplier * 100
    return int(amount) if amount == amount.to_integral_value() else None


def expand_date_excerpt(quote: str, message: str) -> str:
    """Resolve an abbreviated date quote only from unique, ordered exact anchors.

    This repairs citation formatting, not the extracted dates or their meaning.
    Fuzzy matches, reordered words and ambiguous anchors are never accepted.
    """
    if quote.casefold() in message.casefold():
        return quote
    parts = re.split(r"\s*(?:\.{3}|…)\s*", quote)
    if not 2 <= len(parts) <= 4 or any(len(part) < 3 for part in parts):
        return quote
    spans = []
    for part in parts:
        matches = list(re.finditer(re.escape(part), message, re.IGNORECASE))
        if len(matches) != 1:
            return quote
        spans.append(matches[0].span())
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        return quote
    exact = message[spans[0][0] : spans[-1][1]]
    return exact if len(exact) <= 500 else quote


def apply_intent(spec: TripSpec, intent: Intent, message: str) -> TripSpec:
    # An unresolved interpretation is a question, never an implicit mutation.
    if intent.questions:
        return spec.model_copy(deep=True)
    patch = intent.patch.model_dump(mode="json", exclude_unset=True)
    previous = spec.model_dump(mode="json")
    # Some small models repeat known values. Exact no-ops are harmless and need
    # no new evidence; actual changes still require a user excerpt.
    for key in list(patch):
        if key in {
            "travellers",
            "hard_constraints",
            "hotel_preferences",
        } and isinstance(patch[key], dict):
            patch[key] = {
                nested: value
                for nested, value in patch[key].items()
                if value != previous[key].get(nested)
            }
            if not patch[key]:
                del patch[key]
        elif patch[key] == previous[key]:
            del patch[key]
    for key, value in patch.items():
        if value is None and key not in {
            "destination",
            "dates",
            "budget",
            "expense_reserve",
        }:
            raise ValueError(f"cannot clear {key}; omit unchanged fields")
    edits = set(patch)
    for key in (
        "shift_days",
        "optimization",
        "add_preferences",
        "remove_preferences",
        "add_locks",
        "remove_locks",
        "remove_hotel_preferences",
    ):
        if getattr(intent, key):
            edits.add(key)
    errors = []
    for key in sorted(edits):
        quote = intent.evidence.get(key, "")
        if key == "dates":
            quote = expand_date_excerpt(quote, message)
        # Amount and scope may share the same exact budget excerpt, but only if
        # it explicitly names a scope. Do not infer scope from a bare amount.
        if key == "budget_scope" and not quote:
            budget_quote = intent.evidence.get("budget", "")
            if re.search(
                r"на вс[её]|на отель|только.*отел|дорог|трансфер|сбор",
                budget_quote,
                re.IGNORECASE,
            ):
                quote = budget_quote
        if not quote or quote.casefold() not in message.casefold():
            errors.append(
                f"missing exact user evidence for {key}: {quote!r} is not a verbatim quote. "
                "Copy the original words, not a summary; you may quote the whole original sentence containing the requirement."
            )
        if (
            key == "budget_period"
            and patch[key] == "night"
            and not has_nightly_evidence(quote)
        ):
            errors.append(
                "budget_period: night requires an explicit PER NIGHT amount, e.g. за ночь. 'на 5 ночей' is a stay length, NOT a nightly budget. Omit budget_period or use stay with evidence for the total budget."
            )
        if key == "dates" and patch[key] is not None:
            numeric_day = re.search(
                r"(?<!\d)(?:3[01]|[12]\d|0?[1-9])(?!\d)(?!\s*(?:дн|день|ноч|недел|месяц))",
                quote,
                re.IGNORECASE,
            )
            ordinal_day = re.search(
                r"первого|второго|третьего|четв[её]ртого|пятого|шестого|седьмого|восьмого|девятого|десятого|надцатого|двадцатого|тридцатого",
                quote,
                re.IGNORECASE,
            )
            if not numeric_day and not ordinal_day:
                errors.append(
                    "dates: exact calendar days are not in the quote; omit dates and keep duration_days, never invent the first day of a month"
                )
        if key in {"budget", "expense_reserve"} and patch[key] is not None:
            amount = explicit_ruble_amount(quote)
            if amount is not None and patch[key]["amount_minor"] != amount:
                errors.append(
                    f"{key}.amount_minor must be {amount} kopecks from the quoted rouble amount"
                )
    if errors:
        raise ValueError("; ".join(errors))
    result = spec.model_dump(mode="json")
    for key, value in patch.items():
        if key in {"travellers", "hard_constraints", "hotel_preferences"}:
            if key != "hotel_preferences" and any(v is None for v in value.values()):
                raise ValueError(f"omit unchanged nested fields in {key}")
            if key == "hard_constraints" and "other" in value:
                value["other"] = list(
                    dict.fromkeys(result[key]["other"] + value["other"])
                )
            result[key].update(value)
        else:
            result[key] = value
    if intent.shift_days:
        if "dates" in patch:
            raise ValueError("dates and shift_days are mutually exclusive")
        if not spec.dates:
            raise ValueError("cannot shift unknown dates")
        result["dates"] = {
            "start": (spec.dates.start + timedelta(days=intent.shift_days)).isoformat(),
            "end": (spec.dates.end + timedelta(days=intent.shift_days)).isoformat(),
        }
    for field, add, remove in (
        ("preferences", intent.add_preferences, intent.remove_preferences),
        ("locked_component_ids", intent.add_locks, intent.remove_locks),
    ):
        result[field] = list(
            dict.fromkeys([v for v in result[field] if v not in remove] + add)
        )
    for key in intent.remove_hotel_preferences:
        result["hotel_preferences"][key] = None
    # Keep the whole-trip ceiling when the user adds a separate hotel ceiling.
    if (
        ("budget" in patch or "budget_scope" in patch)
        and not result.get("trip_budget")
        and previous.get("budget_scope") in {"booking", "whole_trip"}
    ):
        result["trip_budget"] = previous.get("budget")
        result["include_transport"] = True
    if "budget" in patch or "budget_scope" in patch:
        scope = result.get("budget_scope")
        if scope in {"booking", "whole_trip"}:
            result["trip_budget"] = result["budget"]
            result["include_transport"] = True
        else:
            result["hotel_budget"] = result["budget"]
    if patch.get("include_transport") is False:
        result["include_transport"] = False
        result["trip_budget"] = None
        if result.get("budget_scope") in {"booking", "whole_trip"}:
            result["budget"] = result.get("hotel_budget")
            result["budget_scope"] = "hotel"
    return TripSpec.model_validate(result)


class Check(Model):
    code: Text
    status: Literal["pass", "fail", "unknown"]
    message: Text


class Evidence(Model):
    id: Text
    subject: Text
    source_kind: Literal["verified_public", "synthetic", "live", "unknown"]
    source_url: str | None = None
    checked_at: str
    scope: Text


class Plan(Model):
    id: Text
    dates: Dates | None = None
    component_ids: list[Text]
    breakdown: dict[str, Money]
    total: Money
    checks: list[Check]
    evidence: list[Evidence]
    tradeoffs: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def total_matches(self):
        if (
            not self.breakdown
            or sum(v.amount_minor for v in self.breakdown.values())
            != self.total.amount_minor
        ):
            raise ValueError("plan total must match breakdown")
        return self


class State(Model):
    selected_hotel: dict | None = None
    search_url: str | None = None
    selection: dict = Field(default_factory=dict)
    hotel_options: list[dict] = Field(default_factory=list)
    assistant_message: str = ""
    questions: list[str] = Field(default_factory=list)
    search_mode: Literal["trip", "hotels"] = "trip"
    schema_version: Literal["0.2"] = "0.2"
    revision: Annotated[StrictInt, Field(ge=0)] = 0
    trip_spec: TripSpec = Field(default_factory=TripSpec)
    selected_plan: Plan | None = None
    history: list[Text] = Field(default_factory=list, max_length=10)


class ChangePreview(Model):
    baseline_plan_id: Text
    proposed_plan: Plan
    changed: list[str]
    preserved: list[str]
    price_delta: StrictInt
    tradeoffs: list[str]
    based_on_revision: StrictInt


class Telemetry(Model):
    model: str
    provider: str
    prompt_version: str
    model_calls: int = 0
    tool_calls: list[str] = Field(default_factory=list)
    first_useful_ms: int | None = None
    total_ms: int = 0
    model_ms: int = 0
    sources_ms: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    cost: None = None


class AgentTurn(Model):
    selection: dict = Field(default_factory=dict)
    hotel_options: list[dict] = Field(default_factory=list)
    search_url: str | None = None
    schema_version: Literal["0.2"] = "0.2"
    based_on_revision: int
    status: Literal["needs_input", "choosing", "no_solution", "error"]
    trip_spec: TripSpec
    patch: dict = Field(default_factory=dict)
    assistant_message: str
    questions: list[str] = Field(default_factory=list)
    destination_options: list[dict] = Field(default_factory=list)
    options: list[Plan] = Field(default_factory=list)
    change_preview: ChangePreview | None = None
    # Only the authoritative backend may allow checkout or create bookings.
    checkout_allowed: Literal[False] = False
    booking: None = None
    error_code: str | None = None
    data_mode: str
    telemetry: Telemetry


class DemoBooking(Model):
    demo_booking_id: Text
    plan_id: Text
    total: Money
    is_demo: Literal[True] = True


class Snapshot(Model):
    share: dict | None = None
    transfer_addon_preview: dict | None = None
    journey_recovery: dict | None = None
    journey_preview: dict | None = None
    messages: list[dict] = Field(default_factory=list, max_length=100)
    search_title: str | None = None
    selected_hotel: dict | None = None
    hotel_booking: dict | None = None
    selection: dict = Field(default_factory=dict)
    search_mode: Literal["trip", "hotels"] = "trip"
    hotel_options: list[dict] = Field(default_factory=list)
    search_url: str | None = None
    """Public Core response contract; persistence/authorization stay in Go Core."""
    schema_version: Literal["0.2"] = "0.2"
    session_id: Text
    revision: Annotated[StrictInt, Field(ge=0)]
    request_id: Text
    status: Literal[
        "needs_input",
        "choosing",
        "ready",
        "no_solution",
        "error",
        "booked_demo",
        "hotel_checkout",
        "hotel_booked",
    ]
    trip_spec: TripSpec
    assistant_message: str
    questions: list[str] = Field(default_factory=list)
    destination_options: list[dict] = Field(default_factory=list)
    options: list[Plan] = Field(default_factory=list)
    selected_plan: Plan | None = None
    change_preview: ChangePreview | None = None
    checkout_allowed: StrictBool = False
    booking: DemoBooking | None = None
    data_mode: str
    history: list[Text] = Field(default_factory=list, max_length=10)
    telemetry: Telemetry | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def consistent_checkout(self):
        if self.checkout_allowed and (
            self.status != "ready"
            or not self.selected_plan
            or self.change_preview
            or self.booking
        ):
            raise ValueError(
                "checkout requires a ready selected plan without pending changes or booking"
            )
        if self.status == "hotel_checkout" and (
            not self.selected_hotel or self.hotel_booking
        ):
            raise ValueError("hotel checkout requires a selected hotel")
        if (self.status == "hotel_booked") != (self.hotel_booking is not None):
            raise ValueError("hotel booking and status must agree")
        if self.hotel_booking and self.hotel_booking.get("is_demo") is not True:
            raise ValueError("only prototype hotel booking is supported")
        if (self.status == "booked_demo") != (self.booking is not None):
            raise ValueError("booked_demo and booking must agree")
        return self
