import unittest
import json

from test_agent import FakeModel, full_spec
from travel_agent.demo_tools import DemoTools
from concurrent import futures

import grpc

from main import PredictorServicer
from proto import predict_pb2, predict_pb2_grpc


class PredictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        predict_pb2_grpc.add_PredictorServicer_to_server(
            PredictorServicer(model=FakeModel({}), tools=DemoTools()), cls.server
        )
        port = cls.server.add_insecure_port("127.0.0.1:0")
        cls.server.start()
        cls.channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        grpc.channel_ready_future(cls.channel).result(timeout=5)
        cls.stub = predict_pb2_grpc.PredictorStub(cls.channel)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop(0).wait(timeout=5)

    def test_predict_preserves_authenticated_caller(self):
        response = self.stub.Predict(
            predict_pb2.PredictRequest(name=" Alice ", caller="123"), timeout=5
        )
        self.assertEqual(response.message, "hello Alice from agent")
        self.assertEqual(response.caller, "123")

    def test_empty_name_and_caller(self):
        response = self.stub.Predict(predict_pb2.PredictRequest(name="   "), timeout=5)
        self.assertEqual(response.message, "hello friend from agent")
        self.assertEqual(response.caller, "unknown")

    def test_run_turn_over_real_grpc(self):
        reply = self.stub.RunTurn(
            predict_pb2.TurnRequest(
                message="подбери поездку",
                caller="123",
                state_json=json.dumps(
                    {"trip_spec": full_spec().model_dump(mode="json")}
                ),
            ),
            timeout=5,
        )
        turn = json.loads(reply.turn_json)
        self.assertEqual(reply.caller, "123")
        self.assertEqual(turn["status"], "choosing")
        self.assertEqual(turn["data_mode"], "synthetic")
        self.assertFalse(turn["checkout_allowed"])

    def test_run_turn_rejects_bad_state(self):
        for caller, state, code in (
            ("", "{}", grpc.StatusCode.UNAUTHENTICATED),
            ("123", '{"revision":-1}', grpc.StatusCode.INVALID_ARGUMENT),
        ):
            with self.assertRaises(grpc.RpcError) as error:
                self.stub.RunTurn(
                    predict_pb2.TurnRequest(
                        message="тест", caller=caller, state_json=state
                    ),
                    timeout=5,
                )
            self.assertEqual(error.exception.code(), code)

    def test_evaluate_uses_catalogue_without_model(self):
        reply = self.stub.Evaluate(
            predict_pb2.EvaluateRequest(
                state_json=json.dumps(
                    {"trip_spec": full_spec().model_dump(mode="json")}
                ),
                caller="123",
            ),
            timeout=5,
        )
        turn = json.loads(reply.turn_json)
        self.assertEqual(len(turn["options"]), 3)
        self.assertEqual(turn["telemetry"]["model_calls"], 0)
        self.assertEqual(turn["options"][0]["total"]["amount_minor"], 10900000)


if __name__ == "__main__":
    unittest.main()
