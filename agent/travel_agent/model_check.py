"""Exercise the configured model; never print credentials or provider responses."""
import asyncio
import json

from .domain import State
from .model import ModelError, QwenModel, Settings
from .runner import run_turn
from .demo_tools import DemoTools


async def check():
    settings = Settings.from_env()
    try:
        turn = await run_turn(State(), "Из Москвы", DemoTools(), QwenModel(settings))
        if turn.status == "error":
            raise ModelError(turn.error_code or "model_unavailable")
        if turn.trip_spec.origin != "Москва":
            raise ModelError("unexpected_extraction")
    except ModelError as error:
        print(json.dumps({"status": "error", "code": error.code}))
        return False
    except ValueError:
        print(json.dumps({"status": "error", "code": "model_invalid_json"}))
        return False
    print(json.dumps({"status": "ok", "provider": settings.provider, "model": settings.model}))
    return True


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(check()) else 1)
