import unittest
from travel_agent.domain import TripSpec,apply_intent
from travel_agent.fast_intent import clarify_ambiguous_request


class AmbiguousFollowups(unittest.TestCase):
    def test_alternative_budgets_require_clarification_and_preserve_the_old_limit(self):
        old=TripSpec(budget={'amount_minor':12000000},budget_scope='hotel',hotel_preferences={'pool':True})
        for text in ['До 40 или 60 тысяч рублей, ещё не решили','40 тысяч или 60 тысяч рублей','Бюджет 40 000 либо 60 000 рублей']:
            intent=clarify_ambiguous_request(text)
            self.assertIsNotNone(intent,text)
            self.assertTrue(intent.questions)
            self.assertEqual(apply_intent(old,intent,text),old)

    def test_reversed_same_month_date_interval_is_a_question_not_a_model_error(self):
        for text in ['С 20 по 15 ноября 2026','20–15 ноября 2026','С 15 по 15 декабря']:
            intent=clarify_ambiguous_request(text)
            self.assertIsNotNone(intent,text)
            self.assertTrue(intent.questions)

    def test_valid_budget_corrections_and_cross_month_dates_are_not_rejected(self):
        for text in ['Было 40 тысяч рублей, теперь 60 тысяч','С 20 ноября по 15 декабря 2026','С 10 по 15 ноября 2026']:
            self.assertIsNone(clarify_ambiguous_request(text),text)

if __name__ == "__main__":
    unittest.main()
