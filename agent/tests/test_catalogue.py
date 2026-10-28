import unittest

from travel_agent.demo_tools import DemoTools
from travel_agent.domain import TripSpec
from travel_agent.tools import allowed


def spec(start="2026-11-03", end="2026-11-07", destination="Ярославль"):
    return TripSpec(
        origin="Москва",
        destination=destination,
        dates={"start": start, "end": end},
        travellers={"adults": 2},
        budget={"amount_minor": 20000000},
        budget_scope="booking",
    )


class CatalogueTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_dates_and_city_share_the_same_tool_path(self):
        tools = DemoTools()
        for start, end in [
            ("2026-11-03", "2026-11-07"),
            ("2026-12-20", "2026-12-31"),
            ("2026-11-30", "2026-12-01"),
        ]:
            request = spec(start, end)
            plans = await tools.search_packages(request)
            self.assertEqual(len(plans), 3)
            for plan in plans:
                self.assertEqual(plan.dates, request.dates)
                self.assertTrue(allowed(plan, request))
                self.assertEqual(
                    plan.total.amount_minor,
                    sum(m.amount_minor for m in plan.breakdown.values()),
                )
                self.assertEqual(plan.evidence[0].source_kind, "synthetic")

    async def test_changing_duration_changes_identity_and_hotel_cost(self):
        tools = DemoTools()
        short = (await tools.search_packages(spec("2026-11-10", "2026-11-12")))[0]
        long_request = spec("2026-11-10", "2026-11-17")
        long = (await tools.search_packages(long_request))[0]
        self.assertNotEqual(short.id, long.id)
        self.assertEqual(
            short.breakdown["hotel"].amount_minor * 7,
            long.breakdown["hotel"].amount_minor * 2,
        )
        self.assertFalse(
            allowed(await tools.validate_plan(short, long_request), long_request)
        )

    async def test_catalogue_boundaries_do_not_fabricate_availability(self):
        tools = DemoTools()
        for start, end in [
            ("2026-10-31", "2026-11-03"),
            ("2026-12-30", "2027-01-02"),
            ("2026-11-01", "2026-11-16"),
        ]:
            self.assertEqual(await tools.search_packages(spec(start, end)), [])

    async def test_legacy_quotes_and_forged_dates(self):
        tools = DemoTools()
        request = spec("2026-11-10", "2026-11-15", "Сочи")
        plan = (await tools.search_packages(request))[0]
        self.assertEqual(plan.id, "sochi:2026-11-10:A")
        self.assertEqual(plan.total.amount_minor, 10900000)
        forged = plan.model_copy(update={"dates": spec().dates})
        checked = await tools.validate_plan(forged, request)
        self.assertEqual(checked.dates, request.dates)

    async def test_change_with_variable_length_retains_variant_and_constraints(self):
        tools = DemoTools()
        request = spec()
        baseline = (await tools.search_packages(request))[0]
        request.dates = {"start": "2026-11-05", "end": "2026-11-09"}
        request.hard_constraints.free_cancellation = True
        change = await tools.propose_change(baseline.id, request)
        self.assertTrue(change.candidates[0].id.endswith(":A"))
        self.assertTrue(allowed(change.candidates[0], request))

    async def test_children_and_pets_still_need_confirmed_inventory(self):
        tools = DemoTools()
        for kind in ["child", "pet"]:
            request = spec()
            if kind == "child":
                request.travellers.children = [7]
            else:
                request.hard_constraints.pets = True
            self.assertFalse(
                any(allowed(p, request) for p in await tools.search_packages(request))
            )
