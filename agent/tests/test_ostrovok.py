import json
import unittest
from unittest.mock import AsyncMock, patch

from travel_agent.domain import State, TripSpec
from travel_agent.ostrovok import parse_hotels, search_hotels, search_url
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from travel_agent.tools import ToolError
from test_agent import FakeModel


class PublicHotelsTests(unittest.IsolatedAsyncioTestCase):
    def test_rates_are_not_used_as_availability(self):
        hotel = dict(id='real_hotel', masterId=123, name='Отель',
                     images=[{'tmpl': 'https://cdn.ostrovok.ru/t/{size}/real.jpg'}],
                     datelessRate={'amount': 1000}, datefullRate=None,
                     location={'address': 'Сочи'}, rating=9.1, numReviews=10, nearestBeaches=None)
        page={'props':{'pageProps':{'searchRegionData':{'catalogSlug':'russia/sochi'},'serpData':{'hotels':[hotel,hotel]}}}}
        html='<script id="__NEXT_DATA__" type="application/json">'+json.dumps(page)+'</script>'
        result=parse_hotels(html,'sochi')
        self.assertEqual(len(result),1)
        self.assertNotIn('datelessRate',result[0])
        self.assertNotIn('price',result[0])
        self.assertEqual(result[0]['url'],'https://ostrovok.ru/hotel/russia/sochi/mid123/real_hotel/')
        with self.assertRaises(ToolError):parse_hotels(html,'kazan')

    def test_dates_and_guests_passed_without_claiming_a_rate(self):
        spec=TripSpec(destination='Сочи',dates={'start':'2026-11-10','end':'2026-11-15'},travellers={'adults':2})
        url=search_url('sochi',spec)
        self.assertIn('dates=10.11.2026-15.11.2026',url)
        self.assertIn('guests=2',url)
        spec.travellers.children=[None]
        self.assertNotIn('guests=',search_url('sochi',spec))

    async def test_user_url_never_becomes_fetch_target(self):
        with patch('travel_agent.ostrovok.httpx.AsyncClient') as client:
            with self.assertRaises(ToolError):await search_hotels(TripSpec(destination='http://127.0.0.1/secret'))
            client.assert_not_called()

    async def test_model_drives_public_tool_with_hotel_requirements(self):
        model=FakeModel({'destination':'Сочи','evidence':{'destination':'Сочи'}})
        with patch('travel_agent.ostrovok.search_hotels',new_callable=AsyncMock,return_value=([{'id':'real','name':'Отель','reference_nightly_minor':300000}],'https://ostrovok.ru/hotel/russia/sochi/')) as search:
            turn=await run_turn(State(search_mode='hotels',trip_spec=TripSpec(travellers={'adults':2},stay_nights=5,budget={'amount_minor':4000000})),'Сочи',DemoTools(),model)
            self.assertEqual(turn.status,'choosing')
            self.assertEqual(turn.data_mode,'public_catalogue_demo_rates')
            self.assertEqual(turn.hotel_options[0]['id'],'real')
            self.assertEqual(turn.hotel_options[0]['quote']['source_kind'],'demo')
            self.assertEqual(turn.options,[])
            self.assertFalse(turn.checkout_allowed)
            self.assertEqual(search.call_args.args[0].destination,'Сочи')
            self.assertEqual(turn.telemetry.tool_calls,['ostrovok_public_search'])

    async def test_empty_city_is_asked_without_fetching(self):
        with patch('travel_agent.ostrovok.search_hotels',new_callable=AsyncMock) as search:
            turn=await run_turn(State(search_mode='hotels'),'Хочу отдохнуть',DemoTools(),FakeModel({}))
            self.assertEqual(turn.status,'needs_input')
            search.assert_not_awaited()

    async def test_catalogue_failure_never_falls_back_to_synthetic_prices(self):
        with patch('travel_agent.ostrovok.search_hotels',new_callable=AsyncMock,side_effect=ToolError('Каталог недоступен')):
            turn=await run_turn(State(search_mode='hotels',trip_spec=TripSpec(travellers={'adults':2},stay_nights=5,budget={'amount_minor':4000000})),'Сочи',DemoTools(),FakeModel({'destination':'Сочи','evidence':{'destination':'Сочи'}}))
            self.assertEqual(turn.status,'error')
            self.assertEqual(turn.options,[])
            self.assertEqual(turn.hotel_options,[])
            self.assertFalse(turn.checkout_allowed)
