FROM python:3.12-slim-bookworm
WORKDIR /app
RUN python -m pip install --no-cache-dir grpcio protobuf grpcio-tools
RUN useradd -u 10001 -m appuser
COPY . .
RUN python -m grpc_tools.protoc -I/app --python_out=/app --grpc_python_out=/app /app/proto/predict.proto
USER appuser
EXPOSE 50051
CMD ["python", "main.py"]
