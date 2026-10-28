import unittest
from travel_agent.domain import TripSpec,Intent,apply_intent
from travel_agent.grounding import ground_intent


class RetainedAmenities(unittest.TestCase):
    def test_removing_pool_cannot_remove_explicitly_retained_parking(self):
        old=TripSpec(hotel_preferences={'pool':True,'parking':True})
        for text in ['Убери требование бассейна, парковку сохрани','Бассейн не важен. Сохрани парковку','Убери бассейн, оставь парковку']:
            raw=Intent(remove_hotel_preferences=['pool','parking'],evidence={'remove_hotel_preferences':text})
            new=apply_intent(old,ground_intent(raw,text,old),text)
            self.assertIsNone(new.hotel_preferences.pool)
            self.assertTrue(new.hotel_preferences.parking)

    def test_retaining_one_facility_does_not_restore_another(self):
        old=TripSpec(hotel_preferences={'pool':True,'parking':True,'breakfast':True})
        text='Убери бассейн и завтрак, парковку сохрани'
        raw=Intent(remove_hotel_preferences=['pool','parking','breakfast'],evidence={'remove_hotel_preferences':text})
        new=apply_intent(old,ground_intent(raw,text,old),text)
        self.assertIsNone(new.hotel_preferences.pool)
        self.assertIsNone(new.hotel_preferences.breakfast)
        self.assertTrue(new.hotel_preferences.parking)

if __name__ == "__main__":
    unittest.main()
