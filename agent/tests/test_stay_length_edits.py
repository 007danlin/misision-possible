import unittest
from datetime import timedelta
from travel_agent.domain import Intent,State,TripSpec,apply_intent
from travel_agent.fast_intent import fast_intent


class StayLengthEdits(unittest.TestCase):
    def spec(self,**extra):
        return TripSpec(**({'origin':'Москва','destination':'Сочи','dates':{'start':'2026-11-10','end':'2026-11-15'},'travellers':{'adults':2,'children':[7]},'budget':{'amount_minor':9000000},'budget_scope':'hotel','hotel_preferences':{'pool':True},'preferences':['тихо']}|extra))

    def test_exact_night_correction_changes_checkout_and_preserves_every_other_condition(self):
        for old_nights in (None,3,5):
            for nights in (2,3,5,7,13,30,60):
                with self.subTest(old=old_nights,new=nights):
                    old=self.spec(stay_nights=old_nights)
                    text=f'На {nights} ночей'
                    intent=fast_intent(State(search_mode='hotels',trip_spec=old),text)
                    new=apply_intent(old,intent,text)
                    self.assertEqual(new.dates.start,old.dates.start)
                    self.assertEqual(new.dates.end,old.dates.start+timedelta(days=nights))
                    self.assertEqual(new.stay_nights,nights)
                    self.assertEqual(new.model_dump(exclude={'dates','stay_nights'}),old.model_dump(exclude={'dates','stay_nights'}))

    def test_explicit_day_count_changes_checkout_using_calendar_days(self):
        for days in (2,4,8):
            old=self.spec(stay_nights=5,duration_days=6)
            text=f'Теперь на {days} дня'
            intent=Intent(patch={'duration_days':days},evidence={'duration_days':text})
            new=apply_intent(old,intent,text)
            self.assertEqual((new.dates.end-new.dates.start).days,days-1)
            self.assertEqual(new.stay_nights,days-1)
            self.assertEqual(new.duration_days,days)

    def test_explicit_interval_updates_stale_lengths_but_keeps_explicit_conflicts(self):
        old=self.spec(stay_nights=5,duration_days=6)
        dates={'start':'2026-12-08','end':'2026-12-12'}
        text='С 8 по 12 декабря 2026'
        new=apply_intent(old,Intent(patch={'dates':dates},evidence={'dates':text}),text)
        self.assertEqual(new.stay_nights,4)
        self.assertEqual(new.duration_days,5)
        text+=' на семь дней'
        new=apply_intent(old,Intent(patch={'dates':dates,'duration_days':7},evidence={'dates':text,'duration_days':text}),text)
        self.assertEqual(new.duration_days,7)  # Contradiction stays visible for clarification.

if __name__ == "__main__":
    unittest.main()
