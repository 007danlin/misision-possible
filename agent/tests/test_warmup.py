import asyncio
import os
import unittest
from unittest.mock import patch

from travel_agent.model import Settings
from travel_agent import warmup as startup


class WarmupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cold_prefill_has_its_own_budget(self):
        class SlowPrefill:
            settings = Settings(timeout=1)

            async def extract(self, context, repair, timeout, *, prefill=False):
                if not prefill:
                    raise AssertionError("startup must not generate a user answer")
                async with asyncio.timeout(timeout):
                    # Longer than a user turn's budget, within setup's budget.
                    await asyncio.sleep(1.05)
                return "", {}

        with (
            patch.dict(os.environ, {"MODEL_WARMUP_TIMEOUT_SECONDS": "3"}),
            patch.object(startup, "QwenModel", return_value=SlowPrefill()),
        ):
            await startup.warmup()

    def test_invalid_startup_timeout_uses_safe_default(self):
        for value in ("invalid", "0", "-1", "901", "nan", "inf"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"MODEL_WARMUP_TIMEOUT_SECONDS": value}),
            ):
                self.assertEqual(startup.startup_timeout(), 300)
