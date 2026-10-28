import unittest
from travel_agent.domain import Intent,State,TripSpec,apply_intent
from travel_agent.fast_intent import fast_intent,protect_duration_units


class DurationUnits(unittest.TestCase):
    def test_short_day_reply_does_not_mean_nights(self):
        old=TripSpec(dates={'start':'2026-11-10','end':'2026-11-17'},stay_nights=7)
        for text in ['На четыре дня','на 4 дня','4 дня']:
            intent=fast_intent(State(search_mode='hotels',trip_spec=old),text)
            new=apply_intent(old,intent,text)
            self.assertEqual(new.duration_days,4)
            self.assertEqual(new.stay_nights,3)
            self.assertEqual(str(new.dates.end),'2026-11-13')

    def test_day_and_night_model_confusion_is_repaired_from_the_exact_phrase(self):
        for text,wrong,right,value in [('На четыре дня, нужен завтрак','stay_nights','duration_days',4),('На три ночи, нужен бассейн','duration_days','stay_nights',3)]:
            intent=Intent(patch={wrong:value},evidence={wrong:text})
            fixed=protect_duration_units(intent,text)
            self.assertNotIn(wrong,fixed.patch.model_dump(exclude_unset=True))
            self.assertEqual(getattr(fixed.patch,right),value)
            self.assertIn(fixed.evidence[right],text)

    def test_three_day_shift_keeps_length_instead_of_becoming_a_three_day_trip(self):
        old=TripSpec(dates={'start':'2026-11-10','end':'2026-11-15'})
        for text in ['Сдвинь даты поездки на 3 дня вперёд','Сдвинь на 3 дня']:
            intent=Intent(shift_days=3,evidence={'shift_days':text})
            new=apply_intent(old,protect_duration_units(intent,text),text)
            self.assertEqual(str(new.dates.start),'2026-11-13')
            self.assertEqual(str(new.dates.end),'2026-11-18')
            self.assertIsNone(new.duration_days)

    def test_relative_shifts_and_ambiguous_durations_are_not_converted(self):
        for text in ['На четыре дня позже','На 3 дня вперёд','На 3 или 5 ночей','Не на четыре дня','На 5 ночей, если будет дёшево','На 4 дня и 5 ночей']:
            self.assertEqual(protect_duration_units(Intent(),text).patch.model_dump(exclude_unset=True),{})

if __name__=='__main__':unittest.main()
