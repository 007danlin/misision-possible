import unittest

from travel_agent.domain import Intent, TripSpec, apply_intent
from travel_agent.grounding import ground_intent, rejected_destination
from travel_agent.inspiration import direction_options


class RejectedDestinationTests(unittest.TestCase):
    def test_rejected_city_cannot_become_destination_or_return_on_followup(self):
        for name, rejection in [('Сочи', 'Сочи не предлагай'), ('Сочи', 'Только не Сочи'),
                                ('Анапа', 'Не предлагай Анапа')]:
            message = 'Хочу в лес, к озеру. ' + rejection + '.'
            intent = Intent(patch={'destination': name, 'travel_setting': 'forest'},
                            evidence={'destination': message, 'travel_setting': message})
            grounded = ground_intent(intent, message, TripSpec())
            spec = apply_intent(TripSpec(), grounded, message)
            self.assertIsNone(spec.destination)
            self.assertTrue(spec.preferences)
            self.assertTrue(all(d['destination'] != name for d in direction_options(spec)))
            # An unrelated later edit retains the exclusion without replaying history.
            changed = apply_intent(spec, Intent(patch={'origin':'Москва'}, evidence={'origin':'Из Москвы'}), 'Из Москвы')
            self.assertTrue(all(d['destination'] != name for d in direction_options(changed)))

    def test_rejecting_current_destination_reopens_selection(self):
        old = TripSpec(destination='Сочи', origin='Москва')
        message = 'Сочи не предлагай'
        grounded = ground_intent(Intent(), message, old)
        result = apply_intent(old, grounded, message)
        self.assertIsNone(result.destination)
        self.assertEqual(result.origin, 'Москва')

    def test_change_of_mind_releases_old_exclusion(self):
        old = TripSpec(origin='Москва', preferences=['сочи не предлагай'])
        message = 'Передумал, едем в Сочи'
        grounded = ground_intent(Intent(patch={'destination':'Сочи'}, evidence={'destination':message}), message, old)
        result = apply_intent(old, grounded, message)
        self.assertEqual(result.destination, 'Сочи')
        self.assertEqual(result.preferences, [])

    def test_negation_does_not_reject_a_positive_city(self):
        for message in ['Не против Сочи', 'Не только Сочи', 'Из Сочи хочу в горы',
                        'В Сочи нужен отель, бассейн не нужен', 'В Сочи, не в Казань']:
            self.assertIsNone(rejected_destination(message, 'Сочи'), message)

