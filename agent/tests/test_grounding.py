import unittest
from travel_agent.domain import Intent, TripSpec, apply_intent
from travel_agent.grounding import ground_intent, explicit_clarification


class GroundingTests(unittest.TestCase):
    def apply(self, message, patch, previous=None, **operations):
        old = previous or TripSpec(
            origin="Москва",
            destination="Сочи",
            include_transport=True,
            budget_scope="booking",
            hotel_preferences={"pool": True},
            hard_constraints={"no_night_flights": True},
        )
        i = Intent(patch=patch, evidence={k: message for k in patch}, **operations)
        fixed = ground_intent(i, message, old)
        return apply_intent(old, fixed, message), fixed

    def test_short_destination_exclusions_survive_origin_followup(self):
        from travel_agent.inspiration import direction_options
        from travel_agent.grounding import rejected_destination

        message = "Хочу в лес, но не на Алтай, не на Селигер и не в Сочи."
        spec, _ = self.apply(message, {"travel_setting": "forest"}, previous=TripSpec())
        self.assertTrue(spec.preferences)
        spec, _ = self.apply("Из Москвы", {"origin": "Москва"}, previous=spec)
        self.assertEqual([d["id"] for d in direction_options(spec)], ["karelia"])
        for text in ("Не только на Алтай", "Хочу на Алтай, не в город", "На Алтай не самолётом"):
            self.assertIsNone(rejected_destination(text, "Алтай"))

    def test_unrelated_restrictions_cannot_leak_from_defaults(self):
        s, _ = self.apply(
            "Требуется бесплатная отмена",
            {
                "hard_constraints": {
                    "free_cancellation": True,
                    "no_night_flights": False,
                    "no_connections": True,
                }
            },
        )
        self.assertTrue(s.hard_constraints.free_cancellation)
        self.assertTrue(s.hard_constraints.no_night_flights)
        self.assertFalse(s.hard_constraints.no_connections)

    def test_explicit_relaxation_is_kept(self):
        s, _ = self.apply(
            "Ночные рейсы теперь разрешены",
            {"hard_constraints": {"no_night_flights": False}},
        )
        self.assertFalse(s.hard_constraints.no_night_flights)

    def test_do_not_drop_a_requirement_on_negated_removal(self):
        s, i = self.apply(
            "Найди дешевле, не убирай бассейн", {}, remove_hotel_preferences=["pool"]
        )
        self.assertTrue(s.hotel_preferences.pool)
        self.assertEqual(i.optimization, "cheaper")

    def test_hotel_only_is_distinct_from_not_only_hotel(self):
        s, _ = self.apply("Нужно только жилье", {})
        self.assertFalse(s.include_transport)
        s, _ = self.apply("Нужен не только отель, но и поезд", {})
        self.assertTrue(s.include_transport)

    def test_paid_tickets_do_not_lock_the_hotel_or_change_budget_scope(self):
        s, _ = self.apply(
            "Билеты уже оплачены, гостиница еще нужна",
            {"keep_hotel": True, "budget_scope": "whole_trip"},
        )
        self.assertTrue(s.transport_owned)
        self.assertTrue(s.include_transport)
        self.assertFalse(s.keep_hotel)
        self.assertEqual(s.budget_scope, "booking")

    def test_unpaid_and_future_payment_are_not_owned_tickets(self):
        for m in ("Билеты не куплены", "Дорогу еще нужно оплатить"):
            s, _ = self.apply(m, {})
            self.assertFalse(s.transport_owned)

    def test_alias_normalization_does_not_invent_origin(self):
        s, _ = self.apply("Хочу в Питер", {"destination": "Питер"})
        self.assertEqual(s.destination, "Санкт-Петербург")
        self.assertEqual(s.origin, "Москва")

    def test_ambiguities_leave_the_plan_unchanged(self):
        old = TripSpec(destination="Казань", budget={"amount_minor": 7000000})
        for m in (
            "Лимит 600 евро, переведи в рубли",
            "Нас то ли трое, то ли пятеро",
            "Обязательно парковка, но гостиница без парковки",
        ):
            i = explicit_clarification(m)
            self.assertIsNotNone(i)
            self.assertTrue(i.questions)
            self.assertEqual(apply_intent(old, i, m), old)

    def test_cheaper_cannot_invent_a_zero_budget(self):
        old = TripSpec(budget={"amount_minor": 12000000})
        s, _ = self.apply(
            "Давай дешевле, остальное как было", {"budget": {"amount_minor": 0}}, old
        )
        self.assertEqual(s.budget, old.budget)

    def test_negative_connection_request_is_a_positive_constraint(self):
        s, _ = self.apply(
            "Никаких пересадок не хочу", {"hard_constraints": {"no_connections": False}}
        )
        self.assertTrue(s.hard_constraints.no_connections)
        s, _ = self.apply(
            "Пересадки теперь допустимы", {"hard_constraints": {"no_connections": True}}
        )
        self.assertFalse(s.hard_constraints.no_connections)

    def test_child_friendly_requirement_does_not_invent_a_guest(self):
        s, _ = self.apply(
            "Дети должны отдыхать ночью, нужны тихие номера",
            {"travellers": {"children": [None]}},
        )
        self.assertEqual(s.travellers.children, [])
        s, _ = self.apply("Едем с ребенком", {"travellers": {"children": [None]}})
        self.assertEqual(s.travellers.children, [None])

    def test_spelled_child_age_is_a_guest_not_just_an_amenity_request(self):
        for phrase, age in [
            ("С нами дочь восьми лет", 8),
            ("Двое взрослых и ребенок пяти лет", 5),
        ]:
            s, _ = self.apply(phrase, {"travellers": {"children": [age]}})
            self.assertEqual(s.travellers.children, [age])
