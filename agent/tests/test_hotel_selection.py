import unittest
from travel_agent.domain import TripSpec, State, Intent, apply_intent
from travel_agent.hotel_selection import select_hotels, demo_quote, missing_hotel_questions
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from test_agent import FakeModel


def spec(**values):
    return TripSpec(travellers={'adults':2},stay_nights=5,budget={'amount_minor':3000000},**values)


def hotel(id,price=500000,pool=True,rating=9,center=500):
    return dict(id=id,name=id,reference_nightly_minor=price,amenity_codes=['has_pool'] if pool else [],
                amenities=['Бассейн'] if pool else [],rating=rating,reviews=50,distance_m=center,stars=4)


class SelectionTests(unittest.TestCase):
    def test_whole_trip_budget_failure_reports_a_useful_minimum(self):
        from test_public_content import base, spec as trip_spec
        from travel_agent.hotel_selection import response_text
        candidate=base()
        baseline=trip_spec()
        matching,_=select_hotels([candidate],baseline)
        self.assertTrue(matching)
        minimum=matching[0]['journey']['total_minor']
        limited=baseline.model_copy(update={'budget':baseline.budget.model_copy(update={'amount_minor':500000})})
        choices,info=select_hotels([candidate],limited)
        self.assertFalse(choices)
        self.assertEqual(info['min_budget_minor'],minimum)
        self.assertIn('общий бюджет',info['rejected'])
        self.assertIn('Самый доступный вариант',response_text(choices,info,limited,{}))

    def test_later_matching_candidate_beats_first_three(self):
        candidates=[hotel('expensive',900000),hotel('no-pool',pool=False),hotel('far',center=8000),hotel('match')]
        results,info=select_hotels(candidates,spec(hotel_preferences={'pool':True,'max_center_m':2000}))
        self.assertEqual([h['id'] for h in results],['match'])
        self.assertEqual(info['considered'],4)
        self.assertEqual(results[0]['quote']['total_minor'],2500000)
        self.assertEqual(results[0]['quote']['source_kind'],'demo')

    def test_no_solution_does_not_relax_preferences(self):
        results,info=select_hotels([hotel('far',center=4000)],spec(hotel_preferences={'max_center_m':1000}))
        self.assertFalse(results)
        self.assertIn('до центра',info['rejected'])

    def test_unknown_amenity_is_not_a_match(self):
        self.assertFalse(select_hotels([hotel('unknown',pool=False)],spec(hotel_preferences={'pool':True}))[0])

    def test_per_night_budget_and_child_rooms(self):
        s=TripSpec(travellers={'adults':3,'children':[7]},stay_nights=4,budget={'amount_minor':1000000},budget_period='night')
        quote=demo_quote(hotel('family',400000),s)
        self.assertEqual(quote['rooms'],2)
        self.assertEqual(quote['total_minor'],3200000)
        self.assertTrue(select_hotels([hotel('family',400000)],s)[0])

    def test_unknown_dates_or_guest_count_is_asked(self):
        self.assertEqual(len(missing_hotel_questions(TripSpec(destination='Сочи'))),1)
        self.assertIn('взрослых',missing_hotel_questions(TripSpec(destination='Сочи'))[0])

    def test_cheap_sort_preserves_all_constraints(self):
        results,_=select_hotels([hotel('best',rating=9.9),hotel('cheap',400000,rating=8.9),hotel('wrong',100000,pool=False)],spec(hotel_preferences={'pool':True}),True)
        self.assertEqual([h['id'] for h in results],['cheap','best'])

    def test_explicit_removal_keeps_other_preferences(self):
        s=spec(hotel_preferences={'pool':True,'parking':True})
        intent=Intent.model_validate({'patch':{'hotel_preferences':{'pool':None}},'evidence':{'hotel_preferences':'Бассейн не важен'}})
        result=apply_intent(s,intent,'Бассейн не важен')
        self.assertIsNone(result.hotel_preferences.pool)
        self.assertTrue(result.hotel_preferences.parking)
        self.assertEqual(result.budget,s.budget)

    def test_explicit_remove_operation_clears_only_named_requirement(self):
        s=spec(hotel_preferences={'pool':True,'parking':True})
        intent=Intent.model_validate({'remove_hotel_preferences':['pool'],'evidence':{'remove_hotel_preferences':'Бассейн больше не обязателен'}})
        result=apply_intent(s,intent,'Бассейн больше не обязателен')
        self.assertIsNone(result.hotel_preferences.pool)
        self.assertTrue(result.hotel_preferences.parking)
        self.assertEqual(result.budget,s.budget)

    def test_budget_change_keeps_dates_and_pool(self):
        s=spec(dates={'start':'2026-11-10','end':'2026-11-15'},hotel_preferences={'pool':True})
        changed=apply_intent(s,Intent.model_validate({'patch':{'budget':{'amount_minor':2500000}},'evidence':{'budget':'25 тысяч'}}),'Теперь 25 тысяч')
        self.assertEqual(changed.dates,s.dates)
        self.assertTrue(changed.hotel_preferences.pool)
        self.assertEqual(changed.travellers,s.travellers)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_hotel_question_preserves_choices_without_fetch(self):
        model=FakeModel({'action':'explain','hotel_reference':2})
        options=[hotel('Первый'),hotel('Второй')]
        for h in options:h['reasons']=['Бассейн в отеле'];h['quote']=demo_quote(h,spec())
        state=State(search_mode='hotels',trip_spec=spec(destination='Сочи'),hotel_options=options)
        result=await run_turn(state,'Почему второй?',DemoTools(),model)
        self.assertIn('Второй',result.assistant_message)
        self.assertNotIn('Первый',result.assistant_message)
        self.assertEqual(result.hotel_options,options)
        self.assertEqual(result.telemetry.tool_calls,[])
