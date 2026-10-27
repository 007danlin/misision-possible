import unittest
from unittest.mock import patch

import httpx

from travel_agent.model import ModelError, QwenModel, Settings


class ModelTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, settings, status=200, body=None):
        captured = []
        def respond(request):
            captured.append(request)
            return httpx.Response(status, json=body or ({"message": {"content": "{}"}, "done_reason": "stop", "prompt_eval_count": 10, "eval_count": 2} if settings.provider == "ollama" else {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"total_tokens": 12}}))
        original_client = httpx.AsyncClient
        def client(**kwargs):
            return original_client(transport=httpx.MockTransport(respond), **kwargs)
        with patch("travel_agent.model.httpx.AsyncClient", side_effect=client):
            result = await QwenModel(settings).extract({"message": "тест"}, None, 2)
        return result, captured

    async def test_qwen_protocol(self):
        import json
        result, calls = await self.invoke(Settings(provider="ollama", base_url="http://localhost:11434/v1"))
        self.assertEqual(result, ("{}", {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}))
        body = json.loads(calls[0].content)
        self.assertEqual(body["format"], "json")
        self.assertFalse(body["think"])
        self.assertEqual(body["options"]["num_ctx"], 8192)
        self.assertEqual(calls[0].url.path, "/api/chat")
        self.assertNotIn("authorization", calls[0].headers)

    async def test_local_llama_protocol_and_repair_context(self):
        import json
        _, calls = await self.invoke(Settings())
        body = json.loads(calls[0].content)
        self.assertEqual(calls[0].url.path, "/v1/chat/completions")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["messages"][1]["content"], "тест")
        self.assertNotIn("authorization", calls[0].headers)

    async def test_llama_timings_keep_only_numeric_counters(self):
        result, _ = await self.invoke(Settings(), body={
            "choices":[{"message":{"content":"{}"},"finish_reason":"stop"}],
            "timings":{"prompt_ms":123.4,"predicted_ms":456.7,"cache_n":2000,
                       "prompt_n":100,"private_text":"not telemetry"}})
        self.assertEqual(result[1], {"prompt_ms":123,"generation_ms":457,
                                     "cached_tokens":2000,"evaluated_prompt_tokens":100})

    async def test_hotel_delta_keeps_references_and_preserves_authoritative_plan(self):
        import json
        captured=[]
        def respond(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200,json={"choices":[{"message":{"content":'{"e":0}'},"finish_reason":"stop"}]})
        original_client=httpx.AsyncClient
        def client(**kwargs):
            return original_client(transport=httpx.MockTransport(respond),**kwargs)
        with patch("travel_agent.model.httpx.AsyncClient",side_effect=client), patch.dict("os.environ",{"HOTEL_COMPACT_WIRE":"1"}):
            for city in ("Сочи","Казань"):
                await QwenModel(Settings()).extract({"search_mode":"hotels","trip_spec":{"destination":city,"travellers":{"adults":3,"children":[3,5,7,10,12]},"hotel_preferences":{"parking":False},"preferences":["подальше от лифта"],"excluded_hotel_ids":["internal-id"]},"last_assistant_message":"Сколько ночей?","displayed_hotels":[{"position":2,"name":"Отель","reasons":["long duplicate reason"]}],"message":"На пять ночей"},None,2)
        self.assertEqual(captured[0]["messages"][0],captured[1]["messages"][0])
        for body,city in zip(captured,("Сочи","Казань")):
            messages=body["messages"]
            self.assertEqual(messages[-1]["role"],"user")
            self.assertTrue(messages[-1]["content"].endswith("НОВОЕ сообщение путешественника (source 0):\nНа пять ночей"))
            reference=messages[1]["content"]
            for value in ("подальше от лифта","Сколько ночей?",'"position":2',"Отель"):
                self.assertIn(value,reference)
            for unchanged in (city,"[3,5,7,10,12]",'"parking":false'):
                self.assertNotIn(unchanged,reference)
            self.assertNotIn("internal-id",reference)
            self.assertNotIn("long duplicate reason",reference)

    def test_extracted_delta_preserves_omitted_money_guests_and_constraints(self):
        from travel_agent.domain import Intent, TripSpec, apply_intent
        old = TripSpec(origin="Тула", destination="Казань", travellers={"adults":3,"children":[3,5,7,10,12]},
                       budget={"amount_minor":15000000}, hotel_preferences={"parking":False},
                       hard_constraints={"no_night_flights":True}, preferences=["подальше от лифта"])
        intent = Intent(patch={"stay_nights":5}, evidence={"stay_nights":"На пять ночей"})
        result = apply_intent(old, intent, "На пять ночей")
        self.assertEqual(result.stay_nights, 5)
        for field in ("origin","destination","travellers","budget","hotel_preferences","hard_constraints","preferences"):
            self.assertEqual(getattr(result,field),getattr(old,field))

    async def test_dashscope_requires_configuration(self):
        with self.assertRaises(ModelError) as error:
            await self.invoke(Settings(provider="dashscope", base_url="https://example.invalid/v1"))
        self.assertEqual(error.exception.code, "model_not_configured")

    async def test_http_errors_are_safe(self):
        for code, expected in ((401, "model_credentials"), (429, "model_rate_limited"), (500, "model_unavailable")):
            with self.assertRaises(ModelError) as error:
                await self.invoke(Settings(), status=code, body={"error": "private provider content"})
            self.assertEqual(str(error.exception), expected)

    async def test_truncated_output_is_not_accepted(self):
        with self.assertRaises(ModelError) as error:
            await self.invoke(Settings(provider="openai_compatible", api_key="test"), body={"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]})
        self.assertEqual(error.exception.code, "model_output_truncated")

    async def test_hosted_protocol(self):
        import json
        _, calls = await self.invoke(Settings(provider="dashscope", api_key="test-key", base_url="https://example.invalid/v1"))
        body = json.loads(calls[0].content)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertFalse(body["enable_thinking"])
        self.assertEqual(calls[0].headers["authorization"], "Bearer test-key")
        self.assertNotIn("test-key", body["messages"][0]["content"])

    def test_flat_extraction_is_losslessly_mapped_to_contract(self):
        import json
        from travel_agent.model import canonical_intent
        from travel_agent.domain import Intent
        raw = {"destination": "Тула", "add_preferences": ["тихо"], "evidence": {"destination": "в Тулу", "add_preferences": "тихо"}}
        mapped = Intent.model_validate_json(canonical_intent(json.dumps(raw)))
        self.assertEqual(mapped.patch.destination, "Тула")
        self.assertEqual(mapped.add_preferences, ["тихо"])
        self.assertEqual(mapped.evidence, raw["evidence"])
        with self.assertRaises(ValueError):
            Intent.model_validate_json(canonical_intent('{"booking":true}'))
