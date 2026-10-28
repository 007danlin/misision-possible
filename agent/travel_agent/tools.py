"""Read-only tool boundary. Backend bindings must validate all authoritative facts."""

from dataclasses import dataclass
from typing import Protocol

from .domain import Plan, TripSpec


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class ChangeCandidates:
    baseline: Plan
    candidates: list[Plan]


class ToolRegistry(Protocol):
    data_mode: str

    async def get_destination_options(self, spec: TripSpec) -> list[dict]: ...
    async def search_packages(self, spec: TripSpec) -> list[Plan]: ...
    async def validate_plan(self, plan: Plan, spec: TripSpec) -> Plan: ...
    async def propose_change(
        self, baseline_id: str, spec: TripSpec, prefer_cheaper: bool = False
    ) -> ChangeCandidates: ...


class UnavailableTools:
    data_mode = "unavailable"

    async def get_destination_options(self, spec):
        raise ToolError(
            "Каталог backend ещё не подключён. Условия поездки разобраны; цены и наличие пока не подтверждены."
        )

    async def search_packages(self, spec):
        return await self.get_destination_options(spec)

    async def validate_plan(self, plan, spec):
        return await self.get_destination_options(spec)

    async def propose_change(self, baseline_id, spec, prefer_cheaper=False):
        return await self.get_destination_options(spec)


def allowed(plan: Plan, spec: TripSpec) -> bool:
    required = {"budget", "dates", "travellers", "transport", "locks"}
    if spec.duration_days is not None:
        required.add("duration")
    required.update(
        k for k, value in spec.hard_constraints.model_dump().items() if value
    )
    checks = {c.code: c.status for c in plan.checks}
    if any(checks.get(k) != "pass" for k in required):
        return False
    if any(c.status == "fail" for c in plan.checks):
        return False
    if not set(spec.locked_component_ids) <= set(plan.component_ids):
        return False
    if not plan.evidence:
        return False
    if spec.budget:
        limit = spec.budget.amount_minor
        if spec.budget_scope == "whole_trip":
            if spec.expense_reserve is None:
                return False
            limit -= spec.expense_reserve.amount_minor
        cost = plan.total.amount_minor
        if spec.budget_scope == "hotel":
            hotel = plan.breakdown.get("hotel")
            if hotel is None:
                return False
            cost = hotel.amount_minor
        if cost > limit:
            return False
    return True
