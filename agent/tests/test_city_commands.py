import unittest
from travel_agent.domain import State, apply_intent
from travel_agent.fast_intent import fast_intent


class CityCommandTests(unittest.TestCase):
    def setUp(self):
        self.state=State(search_mode='hotels',trip_spec={
            'origin':'Москва','destination':'Сочи','dates':{'start':'2026-11-10','end':'2026-11-15'},
            'travellers':{'adults':2,'children':[5,9]},'budget':{'amount_minor':9000000},
            'budget_scope':'hotel','hotel_preferences':{'pool':True},'preferences':['тихо']})

    def test_explicit_departure_updates_are_normalized_and_preserve_every_other_field(self):
        for phrase,city in [
            ('Отправляемся из Питера','Санкт-Петербург'),
            ('Отправляемся из Санкт-Петербурга','Санкт-Петербург'),
            ('Отправляемся из Москвы','Москва'),
            ('Отправляемся из Казани','Казань'),
            ('Отправляемся из Нижнего Новгорода','Нижний Новгород'),
        ]:
            with self.subTest(phrase=phrase):
                intent=fast_intent(self.state,phrase)
                self.assertIsNotNone(intent)
                new=apply_intent(self.state.trip_spec,intent,phrase)
                self.assertEqual(new.origin,city)
                self.assertEqual(new.model_dump(exclude={'origin'}),self.state.trip_spec.model_dump(exclude={'origin'}))

    def test_combined_or_negated_departure_messages_are_not_swallowed_by_shortcut(self):
        for phrase in [
            'Отправляемся из Москвы, но лучше в Казань',
            'Отправляемся из Питера и добавь завтрак',
            'Отправляемся из Москвы. Бюджет 50 тысяч рублей',
            'Отправляемся из Москвы или Казани',
            'Отправляемся из неизвестного города',
        ]:
            self.assertIsNone(fast_intent(self.state,phrase),phrase)

if __name__ == "__main__":
    unittest.main()
