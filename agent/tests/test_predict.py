import unittest
from concurrent import futures

import grpc

from main import PredictorServicer
from proto import predict_pb2, predict_pb2_grpc


class PredictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        predict_pb2_grpc.add_PredictorServicer_to_server(
            PredictorServicer(), cls.server
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
        response = self.stub.Predict(
            predict_pb2.PredictRequest(name="   "), timeout=5
        )
        self.assertEqual(response.message, "hello friend from agent")
        self.assertEqual(response.caller, "unknown")


if __name__ == "__main__":
    unittest.main()
