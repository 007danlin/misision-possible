FROM python:3.12-slim-bookworm@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753 AS builder
WORKDIR /app
COPY pyproject.toml README.md constraints.txt ./
COPY travel_agent ./travel_agent
COPY proto ./proto
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python -m pip install --no-cache-dir -c constraints.txt . grpcio-tools==1.80.0
RUN python -m grpc_tools.protoc -I/app --python_out=/app --grpc_python_out=/app /app/proto/predict.proto

FROM python:3.12-slim-bookworm@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753
WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /opt/venv /opt/venv
RUN python -m pip uninstall -y grpcio-tools setuptools pip \
    && useradd -u 10001 -m appuser \
    && mkdir -p /app/content-cache && chown appuser:appuser /app/content-cache
COPY --from=builder /app/proto ./proto
COPY travel_agent ./travel_agent
COPY main.py healthcheck.py bootstrap.py ./
USER appuser
EXPOSE 50051
CMD ["python", "bootstrap.py"]
