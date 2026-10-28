import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from travel_agent.calendar_followup import calendar_followup
from travel_agent.domain import Intent, State, TripSpec, apply_intent
from travel_agent.fast_intent import fast_intent
from travel_agent.hotel_selection import missing_hotel_questions
from travel_agent.model import hotel_reference_state
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from test_agent import FakeModel


class CalendarFollowupTests(unittest.TestCase):
    def resolve(self, text, spec=None):
        return apply_intent(spec or TripSpec(), calendar_followup(text, date(2026, 10, 28)), text)

    def test_formats_and_arbitrary_lengths_preserve_all_wishes(self):
        for text, start in [("давай на 16 ноября", "2026-11-16"), ("с 31 декабря", "2026-12-31"), ("заезд 16.11.2027", "2027-11-16"), ("2027-01-05", "2027-01-05"), ("завтра", "2026-10-29")]:
            for nights in (2, 5, 13):
                with self.subTest(text=text, nights=nights):
                    old = TripSpec(destination="Санкт-Петербург", stay_nights=nights, travellers={"adults": 2}, budget={"amount_minor": 3500000}, budget_scope="hotel", hotel_preferences={"min_rating": 8.5}, preferences=["поближе к воде"])
                    new = self.resolve(text, old)
                    self.assertEqual(str(new.dates.start), start)
                    self.assertEqual((new.dates.end-new.dates.start).days, nights)
                    for field in ("destination", "travellers", "budget", "budget_scope", "hotel_preferences", "preferences"):
                        self.assertEqual(getattr(new, field), getattr(old, field))

    def test_date_before_duration_survives_serialization(self):
        first = self.resolve("16 ноября", TripSpec(destination="Казань", travellers={"adults": 2}))
        self.assertIsNone(first.dates)
        self.assertIn("На сколько ночей", missing_hotel_questions(first)[0])
        state = State.model_validate_json(State(search_mode="hotels", trip_spec=first).model_dump_json())
        final = apply_intent(state.trip_spec, fast_intent(state, "на 5 ночей"), "на 5 ночей")
        self.assertEqual(str(final.dates.end), "2026-11-21")
        self.assertIsNone(final.checkin_date)

    def test_days_and_same_message_length(self):
        for text, spec in [("16 ноября", TripSpec(duration_days=4)), ("16 ноября на три ночи", TripSpec()), ("16 ноября на 4 дня", TripSpec())]:
            self.assertEqual(str(self.resolve(text, spec).dates.end), "2026-11-19")

    def test_move_uses_actual_interval_not_stale_nights(self):
        spec = TripSpec(stay_nights=2, dates={"start":"2026-11-01", "end":"2026-11-06"})
        self.assertEqual(str(self.resolve("перенеси на 16 ноября", spec).dates.end), "2026-11-21")

    def test_invalid_dates_and_ambiguity(self):
        for text in ("31 апреля", "30 февраля", "2026-02-29", "2020-11-16"):
            self.assertTrue(calendar_followup(text, date(2026, 10, 28)).questions)
        for text in ("в ноябре", "не 16 ноября", "16 или 18 ноября", "если получится 16 ноября", "выезд 16 ноября"):
            self.assertIsNone(calendar_followup(text))
        self.assertEqual(str(self.resolve("29 февраля").checkin_date), "2028-02-29")

    def test_exact_intervals_and_wrong_model_month(self):
        from travel_agent.grounding import ground_intent
        for interval in ('10–15 ноября 2026', 'с 10 по 15 ноября 2026', '10 ноября — 15 ноября 2026'):
            spec = self.resolve(interval)
            self.assertEqual(str(spec.dates.start), '2026-11-10')
            self.assertEqual(str(spec.dates.end), '2026-11-15')
            message = 'Отель в Казани: ' + interval + ', двое взрослых, с завтраком.'
            intent = Intent(patch={'dates': {'start':'2026-10-10','end':'2026-10-15'},
                                   'travellers':{'adults':2}, 'hotel_preferences':{'breakfast':True}},
                            evidence={k:message for k in ('dates','travellers','hotel_preferences')})
            grounded = ground_intent(intent, message, TripSpec())
            result = apply_intent(TripSpec(), grounded, message)
            self.assertEqual(str(result.dates.start), '2026-11-10')
            self.assertEqual(str(result.dates.end), '2026-11-15')
            self.assertEqual(result.travellers.adults, 2)
            self.assertTrue(result.hotel_preferences.breakfast)
        for invalid in ('15–10 ноября 2026', '29–31 февраля 2027', '10–15 ноября 2020'):
            self.assertTrue(calendar_followup(invalid, date(2026,10,28)).questions)
        self.assertIsNone(calendar_followup('Не 10–15 ноября 2026'))
        self.assertIsNone(calendar_followup('10–15 ноября 2026 или 20–25 ноября 2026'))

    def test_waterfront_wish_is_preserved_without_inventing_seaside(self):
        from travel_agent.grounding import ground_intent
        for message in ("хочется поближе к воде", "хочу рядом с рекой", "отель у озера"):
            intent = Intent(patch={"travel_setting": "sea"}, evidence={"travel_setting": message})
            result = apply_intent(TripSpec(), ground_intent(intent, message, TripSpec()), message)
            self.assertEqual(result.travel_setting, "any")
            self.assertEqual(len(result.preferences), 1)
            self.assertIn(result.preferences[0], message)

    def test_model_partial_date_merges_with_saved_duration(self):
        from travel_agent.compact_wire import decode
        from travel_agent.model import canonical_intent

        message = "Приедем 20 декабря 2026, нужен завтрак"
        raw = '{"e":0,"ci":"2026-12-20","breakfast":true}'
        intent = Intent.model_validate_json(canonical_intent(decode(raw, message), message))
        result = apply_intent(TripSpec(stay_nights=7), intent, message)
        self.assertEqual(str(result.dates.end), "2026-12-27")
        self.assertTrue(result.hotel_preferences.breakfast)

    def test_model_has_calendar_context_for_complex_edits(self):
        reference = hotel_reference_state({"stay_nights": 4, "checkin_date": "2026-11-16", "budget": {"amount_minor": 50000}}, "Можем приехать шестнадцатого ноября")
        self.assertEqual(reference, {"stay_nights": 4, "checkin_date": "2026-11-16"})


class CalendarRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_answer_proceeds_to_search_without_model_or_repeated_question(self):
        state = State(search_mode="hotels", trip_spec={"origin":"Москва", "destination":"Санкт-Петербург", "stay_nights":2, "travellers":{"adults":2}, "budget":{"amount_minor":3500000}, "budget_scope":"hotel", "include_transport": True}, assistant_message="На какие точные даты собрать дорогу, отель и трансферы?")
        model = FakeModel()
        with patch("travel_agent.ostrovok.search_hotels", new=AsyncMock(return_value=([], ""))) as search, patch("travel_agent.transport.prepare_road", new=AsyncMock(return_value=None)), patch.dict("os.environ", {"JOURNEY_DATA_SOURCE":"public"}):
            turn = await run_turn(state, "давай на 16 ноября 2027", DemoTools(), model)
        self.assertEqual(str(turn.trip_spec.dates.end), "2027-11-18")
        self.assertEqual(model.calls, 0)
        self.assertNotIn("На какие точные даты", turn.assistant_message)
        search.assert_awaited_once()
