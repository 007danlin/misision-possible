"""Process readiness only; model access is checked separately by model_check.py."""
import os

import grpc
from proto import predict_pb2, predict_pb2_grpc


def main():
    with grpc.insecure_channel("127.0.0.1:" + os.getenv("AGENT_PORT", "50051")) as channel:
        reply = predict_pb2_grpc.PredictorStub(channel).Predict(
            predict_pb2.PredictRequest(name="health", caller="healthcheck"), timeout=3)
        if reply.caller != "healthcheck":
            raise RuntimeError("invalid readiness response")


if __name__ == "__main__":
    main()
