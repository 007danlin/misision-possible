# Agent

Отдельный Python gRPC-сервис. Пока `Predict` возвращает демонстрационное
приветствие; здесь можно реализовать вызов модели или логику агента.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python main.py
```

Порт задаётся через `AGENT_PORT`, по умолчанию 50051. Core передаёт `name`
и `caller` (ID проверенного пользователя), ожидает `message` в ответе.
Контракт: `proto/predict.proto`; копия и Go bindings — в `backend/core/proto/`.
Namespace `model.Predictor` сохранён для совместимости протокола.

После изменения контракта пересоздайте Python bindings (нужен grpcio-tools):

```sh
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/predict.proto
```

Dockerfile выполняет генерацию автоматически при сборке.
