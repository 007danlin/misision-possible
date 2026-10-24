import os

import grpc
from concurrent import futures

from proto import predict_pb2
from proto import predict_pb2_grpc


class PredictorServicer(predict_pb2_grpc.PredictorServicer):
    def Predict(self, request, context):
        name = request.name.strip() or "friend"
        caller = request.caller or "unknown"
        message = f"hello {name} from agent"
        return predict_pb2.PredictReply(message=message, caller=caller)


def serve() -> None:
    port = os.getenv("AGENT_PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    predict_pb2_grpc.add_PredictorServicer_to_server(PredictorServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"agent gRPC server running on :{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
