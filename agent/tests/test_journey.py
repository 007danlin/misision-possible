import copy
import unittest
from unittest.mock import patch

from travel_agent.domain import TripSpec, Intent, apply_intent, State
from travel_agent.hotel_selection import demo_quote, select_hotels, missing_hotel_questions
from travel_agent import journey
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from test_agent import FakeModel
from travel_agent.model import canonical_intent


def spec(**extra):
    return TripSpec(**(dict(origin='Москва', destination='Сочи', dates={'start':'2026-11-10','end':'2026-11-15'}, travellers={'adults':2}, budget={'amount_minor':12000000}, budget_scope='booking', include_transport=True) | extra))


class JourneyTests(unittest.TestCase):
    def test_misplaced_action_repair_is_lossless_and_narrow(self):
        i=Intent.model_validate_json(canonical_intent('{"optimization":{"action":"search"},"budget":{"amount_minor":12000000},"evidence":{"budget":"120 тысяч"}}'))
        self.assertEqual(i.action,'search');self.assertIsNone(i.optimization)
        self.assertEqual(i.patch.budget.amount_minor,12000000)
        for raw in ['{"action":"change","optimization":{"action":"search"}}','{"optimization":{"action":"search","budget":1}}']:
            with self.assertRaises(ValueError):Intent.model_validate_json(canonical_intent(raw))
    def test_total_is_components_and_filters_whole_budget(self):
        s=spec(); hotels,_=select_hotels(journey.candidates(s),s)
        self.assertEqual(len(hotels),3)
        for h in hotels:
            j=h['journey']
            self.assertEqual(j['total_minor'],sum(j['breakdown'].values()))
            self.assertTrue(j['can_book'])
            self.assertEqual(len(j['segments']),4)
        s.budget.amount_minor=1000000
        self.assertEqual(select_hotels(journey.candidates(s),s)[0],[])

    def test_cheaper_hotel_can_cost_more_with_transfer(self):
        s=spec(); hotels,_=select_hotels(journey.candidates(s),s,True)
        by_id={h['id']:h for h in hotels}
        central,remote=by_id['sample-sochi-2'],by_id['sample-sochi-3']
        self.assertLess(remote['quote']['total_minor'],central['quote']['total_minor'])
        self.assertGreater(remote['journey']['total_minor'],central['journey']['total_minor'])
        self.assertEqual(hotels[0]['id'],central['id'])

    def test_overall_budget_survives_hotel_budget_and_reprice(self):
        s=apply_intent(TripSpec(),Intent(patch={'budget':{'amount_minor':12000000},'budget_scope':'booking'}, evidence={'budget':'120 тысяч','budget_scope':'дорога, отель и трансферы'}),'120 тысяч: дорога, отель и трансферы')
        s=apply_intent(s,Intent(patch={'budget':{'amount_minor':4000000},'budget_scope':'hotel'},evidence={'budget':'40 тысяч','budget_scope':'на отель'}),'40 тысяч на отель')
        self.assertEqual(s.trip_budget.amount_minor,12000000)
        self.assertEqual(s.hotel_budget.amount_minor,4000000)
        self.assertTrue(journey.enabled(s))

    def test_late_arrival_is_rejected_and_reprice_exposes_conflict(self):
        s=spec(); h=journey.candidates(s)[0];h['content']['checkin_until']='12:00'
        j=journey.quote(h,s,demo_quote(h,s))
        self.assertFalse(j['can_book'])
        self.assertEqual(next(c for c in j['checks'] if c['code']=='checkin')['status'],'fail')
        self.assertFalse(select_hotels([h],s)[0])

    def test_return_buffer_and_cross_midnight(self):
        s=spec(); route=copy.deepcopy(journey.CATALOGUE['routes']['Сочи']);route['return_departure']='00:30'
        with patch.dict(journey.CATALOGUE['routes'],{'Сочи':route}):
            h=journey.candidates(s)[0];j=journey.quote(h,s,demo_quote(h,s))
            self.assertTrue(j['segments'][2]['departure'].startswith('2026-11-14'))
            s.hard_constraints.no_night_flights=True
            j=journey.quote(h,s,demo_quote(h,s));self.assertFalse(j['can_book'])

    def test_reserved_money_is_not_spendable(self):
        s=spec(budget_scope='whole_trip',budget={'amount_minor':7000000},expense_reserve={'amount_minor':3000000})
        self.assertFalse(select_hotels(journey.candidates(s),s)[0])
        self.assertNotIn('именно для отеля',' '.join(missing_hotel_questions(s)))

    def test_family_reprices_all_services_and_room_capacity(self):
        s=spec(); h=journey.reprice(s,'sample-sochi-1');old=h['journey']['total_minor']
        s.travellers.children=[4,8];s.dates.end=s.dates.end.replace(day=17)
        h=journey.reprice(s,'sample-sochi-1')
        self.assertEqual(h['quote']['rooms'],2)
        self.assertEqual(h['journey']['vehicles'],2)
        self.assertEqual(h['journey']['child_seats'],2)
        self.assertGreater(h['journey']['total_minor'],old)
        self.assertIn('2026-11-17',h['journey']['segments'][-1]['departure'])

    def test_unknown_route_and_hard_requirement_never_pass(self):
        s=spec(origin='Париж');self.assertIsNone(journey.reprice(s,'sample-sochi-1'))
        s=spec(hard_constraints={'other':['полная доступность для коляски']})
        h=journey.reprice(s,'sample-sochi-1');self.assertFalse(h['journey']['can_book'])
        self.assertTrue(select_hotels(journey.candidates(s),s)[0])

    def test_reprice_uses_canonical_price_and_reviews_do_not_leak_to_real_hotel(self):
        s=spec();h=journey.reprice(s,'sample-sochi-1');h['quote']['total_minor']=1
        self.assertGreater(journey.reprice(s,h['id'])['quote']['total_minor'],1)
        self.assertIn('Отзывы можно прочитать',journey.review_answer({'id':'real-hotel'}))


class JourneyConversationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        p=patch.dict("os.environ", {"JOURNEY_DATA_SOURCE":"synthetic"});p.start();self.addCleanup(p.stop)

    async def test_complete_request_never_needs_hotel_allocation_or_external_search(self):
        s=State(search_mode='hotels',trip_spec=spec())
        with patch('travel_agent.ostrovok.search_hotels',side_effect=AssertionError('must stay local')):
            r=await run_turn(s,'Сравни варианты',DemoTools(),FakeModel({'action':'search'}))
        self.assertEqual(r.status,'choosing')
        self.assertTrue(all(h.get('journey') for h in r.hotel_options))

    async def test_locked_hotel_does_not_switch_to_cheaper_property(self):
        s=spec();s.keep_hotel=True;s.locked_hotel_id='sample-sochi-1'
        state=State(search_mode='hotels',trip_spec=s,selected_hotel=journey.reprice(s,s.locked_hotel_id))
        r=await run_turn(state,'Подешевле',DemoTools(),FakeModel({'optimization':'cheaper','evidence':{'optimization':'Подешевле'}}))
        self.assertTrue(all(h['id']=='sample-sochi-1' for h in r.hotel_options))
