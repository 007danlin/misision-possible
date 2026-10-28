import unittest
from unittest.mock import AsyncMock,patch
from travel_agent.domain import State
from travel_agent.demo_tools import DemoTools
from travel_agent.runner import run_turn
from test_agent import FakeModel


class DestinationEditExclusions(unittest.IsolatedAsyncioTestCase):
    async def test_new_destination_never_excludes_hotels_from_the_old_city(self):
        state=State(search_mode='hotels',trip_spec={'destination':'Казань','travellers':{'adults':2},'stay_nights':3,'budget':{'amount_minor':5000000},'budget_scope':'hotel','excluded_hotel_ids':['earlier']},hotel_options=[{'id':'kazan-1','name':'Первый Казань'}])
        with patch('travel_agent.ostrovok.search_hotels',AsyncMock(return_value=([],''))):
            result=await run_turn(state,'Передумал, лучше Питер',DemoTools(),FakeModel({'action':'replace_options','patch':{'destination':'Санкт-Петербург'},'evidence':{'destination':'Питер'}}))
        self.assertEqual(result.trip_spec.destination,'Санкт-Петербург')
        self.assertEqual(result.trip_spec.excluded_hotel_ids,[])
        self.assertEqual(state.trip_spec.excluded_hotel_ids,['earlier'])

if __name__=='__main__':unittest.main()
