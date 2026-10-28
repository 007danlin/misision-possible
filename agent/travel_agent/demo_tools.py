"""Explicit synthetic contract fixture, never enabled as a fallback for model failure.

This is not Luka's production catalogue. It makes the tool boundary executable
until backend catalogue bindings exist. No real availability or booking is implied.
"""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

from .domain import Check, Evidence, Money, Plan
from .tools import ChangeCandidates, ToolError, allowed

CATALOGUE = json.loads(Path(__file__).with_name("catalogue.json").read_text())
CATALOG_VERSION = CATALOGUE["version"]
DESTINATIONS = CATALOGUE["destinations"]


def supported_dates(start, end):
    return (
        date.fromisoformat(CATALOGUE["start"])
        <= start
        < end
        <= date.fromisoformat(CATALOGUE["end"])
        and 1 <= (end - start).days <= CATALOGUE["max_nights"]
    )


def evidence(subject):
    return Evidence(
        id="demo:" + subject,
        subject=subject,
        source_kind="synthetic",
        checked_at=datetime.now(timezone.utc).isoformat(),
        scope=f"{CATALOG_VERSION}: учебный набор, не рыночная цена или реальная доступность",
    )


def rubles(amount_minor):
    whole, fraction = divmod(amount_minor, 100)
    text = f"{whole:,}".replace(",", " ")
    return text + (f",{fraction:02d}" if fraction else "") + " ₽"


class DemoTools:
    data_mode = "synthetic"

    async def get_destination_options(self, spec):
        return [
            {
                "id": d["id"],
                "name": name,
                "reason": d["description"],
                "availability": "synthetic_fixture_only",
                "evidence": [evidence("destination:" + d["id"]).model_dump()],
            }
            for name, d in DESTINATIONS.items()
        ]

    @staticmethod
    def _catalogue_plan(plan_id):
        # Resolve all prices, IDs and evidence from the catalogue. A caller's
        # serialized Plan is never an authoritative quote.
        parts = plan_id.split(":")
        if len(parts) not in {3, 4}:
            return None
        destination_id, start, letter = parts[0], parts[1], parts[-1]
        try:
            arrival = date.fromisoformat(start)
            departure = (
                date.fromisoformat(parts[2])
                if len(parts) == 4
                else arrival + timedelta(days=5)
            )
        except ValueError:
            return None
        destination = next(
            (d for d in DESTINATIONS.values() if d["id"] == destination_id), None
        )
        if (
            destination is None
            or not supported_dates(arrival, departure)
            or letter not in {"A", "B", "C"}
        ):
            return None
        prefix = ":".join(parts[:-1])
        costs = dict(
            zip(
                ("transport", "hotel", "transfers", "fees"),
                destination["costs"]["ABC".index(letter)],
            )
        )
        # Transparent synthetic pricing: return transport varies on a seven-day
        # cycle, hotel is the reference five-night price prorated per night.
        costs["transport"] += ((arrival - date(2026, 11, 10)).days % 7) * 1000
        costs["hotel"] = costs["hotel"] * (departure - arrival).days // 5
        components = [
            f"{prefix}:{kind}:{letter if kind != 'transfers' else 'shared'}"
            for kind in costs
        ]
        return Plan(
            id=plan_id,
            dates={"start": arrival, "end": departure},
            component_ids=components,
            breakdown={k: Money(amount_minor=v * 100) for k, v in costs.items()},
            total=Money(amount_minor=sum(costs.values()) * 100),
            checks=[],
            evidence=[evidence(f"{prefix}:{letter}:price_and_terms")],
            tradeoffs=["Все цены, расписание и свойства — учебные."]
            + (
                ["Невозвратный тариф: бесплатная отмена отсутствует."]
                if letter == "B"
                else []
            ),
        )

    async def search_packages(self, spec):
        destination = DESTINATIONS.get(spec.destination)
        if not destination or not spec.dates or spec.origin != CATALOGUE["origin"]:
            return []
        if not supported_dates(spec.dates.start, spec.dates.end):
            return []
        prefix = destination["id"] + ":" + spec.dates.start.isoformat()
        # Keep old five-night IDs so existing saved sessions remain readable.
        if (spec.dates.end - spec.dates.start).days != 5:
            prefix += ":" + spec.dates.end.isoformat()
        return [
            await self.validate_plan(self._catalogue_plan(f"{prefix}:{letter}"), spec)
            for letter in "ABC"
        ]

    async def validate_plan(self, plan, spec):
        canonical = self._catalogue_plan(plan.id)
        plan = canonical or plan.model_copy(deep=True)
        letter = plan.id.rsplit(":", 1)[-1]
        expected_prefix = f"{DESTINATIONS.get(spec.destination, {}).get('id')}:{spec.dates.start if spec.dates else None}:"
        known = (
            canonical is not None
            and plan.id.startswith(expected_prefix)
            and plan.dates == spec.dates
        )

        def check(code, status, text):
            return Check(
                code=code,
                status="pass"
                if status is True
                else "fail"
                if status is False
                else "unknown",
                message=text,
            )

        limit = spec.budget.amount_minor if spec.budget else None
        if spec.budget_scope == "whole_trip":
            limit = (
                limit - spec.expense_reserve.amount_minor
                if limit is not None and spec.expense_reserve
                else None
            )
        cost = (
            plan.breakdown["hotel"].amount_minor
            if spec.budget_scope == "hotel"
            else plan.total.amount_minor
        )
        plan.checks = [
            check(
                "catalogue",
                canonical is not None,
                "Состав, цена и условия заново получены из учебного каталога по ID.",
            ),
            check(
                "budget",
                cost <= limit if limit is not None else None,
                ("Проживание" if spec.budget_scope == "hotel" else "Услуги поездки")
                + ": "
                + rubles(cost)
                + (
                    " при допустимом лимите " + rubles(limit) + "."
                    if limit is not None
                    else "; смысл бюджета или резерв ещё не подтверждены."
                ),
            ),
            check(
                "dates",
                known,
                "Даты сверены с учебным каталогом: ноябрь–декабрь 2026, от 1 до 14 ночей; выезд не позднее 31 декабря.",
            ),
            check(
                "duration",
                spec.duration_days is None
                or (
                    spec.dates is not None
                    and spec.duration_days
                    == (spec.dates.end - spec.dates.start).days + 1
                ),
                "Длительность в календарных днях должна совпадать с точными датами; ночи считаются отдельно.",
            ),
            check(
                "travellers",
                spec.travellers.adults == 2 and not spec.travellers.children,
                "Тариф только для двух взрослых.",
            ),
            check(
                "transport",
                known and spec.origin == "Москва",
                "Учебный путь туда-обратно, оба трансфера и сборы включены.",
            ),
            check(
                "locks",
                set(spec.locked_component_ids) <= set(plan.component_ids),
                "Закреплённые компоненты должны сохраниться.",
            ),
            check(
                "no_night_flights",
                True,
                "Учебные рейсы: туда 10:00–12:00, обратно 15:00–17:00, UTC+03:00; ночных интервалов нет.",
            ),
            check(
                "free_cancellation",
                letter != "B" if spec.hard_constraints.free_cancellation else True,
                "Тариф B невозвратный; A и C — учебная бесплатная отмена.",
            ),
        ]
        if spec.hard_constraints.pets:
            plan.checks.append(check("pets", None, "Данных о размещении питомца нет."))
        if spec.hard_constraints.other:
            plan.checks.append(
                check(
                    "other",
                    None,
                    "Дополнительные жёсткие требования не подтверждены каталогом.",
                )
            )
        return plan

    async def propose_change(self, baseline_id, spec, prefer_cheaper=False):
        baseline = self._catalogue_plan(baseline_id)
        if baseline is None:
            raise ToolError("Выбранная поездка отсутствует в подключённом каталоге.")
        candidates = await self.search_packages(spec)
        plans = [p for p in candidates if allowed(p, spec)]
        # Preserve the current combination unless the user asked for a lower
        # price or the new requirements made it infeasible.
        cheaper = [
            p for p in plans if p.total.amount_minor < baseline.total.amount_minor
        ]
        pool = (cheaper or plans) if prefer_cheaper else plans
        # A date move should retain the same catalogue combination when it is
        # still feasible; date-specific rate IDs alone must not cause a downgrade.
        baseline_city, baseline_variant = (
            baseline.id.split(":")[0],
            baseline.id.split(":")[-1],
        )
        if spec.dates and baseline.dates != spec.dates:
            same_combination = [
                p
                for p in pool
                if p.id.split(":")[0] == baseline_city
                and p.id.split(":")[-1] == baseline_variant
            ]
            if same_combination:
                return ChangeCandidates(baseline, same_combination)
        candidates = (
            sorted(
                pool,
                key=lambda p: (
                    -len(set(p.component_ids) & set(baseline.component_ids)),
                    p.total.amount_minor,
                ),
            )
            or candidates
        )
        return ChangeCandidates(baseline, candidates)
