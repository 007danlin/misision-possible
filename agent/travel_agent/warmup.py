"""Prefill stable hotel instructions; no result is saved as a user answer."""

import asyncio
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .model import QwenModel, Settings


def startup_timeout():
    try:
        value = float(os.getenv("MODEL_WARMUP_TIMEOUT_SECONDS", "300"))
    except ValueError:
        return 300.0
    return value if 1 <= value <= 900 else 300.0


async def warmup():
    model = QwenModel(Settings.from_env())
    context = {
        "today": datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat(),
        "search_mode": "hotels",
        "trip_spec": {},
        "message": "Начать поиск",
        "last_assistant_message": "",
        "last_questions": [],
        "displayed_hotels": [],
    }
    started = time.monotonic()
    timeout = startup_timeout()
    print(json.dumps({"warmup": "starting", "timeout_seconds": timeout}), flush=True)
    _, usage = await model.extract(context, None, timeout, prefill=True)
    print(
        json.dumps(
            {
                "warmup": "ready",
                "seconds": round(time.monotonic() - started, 3),
                "usage": usage,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(warmup())
