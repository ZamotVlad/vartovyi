import asyncio
import contextlib
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.services import scheduler


async def test_failed_tick_does_not_stop_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    third_call = asyncio.Event()

    async def flaky(*args: Any, **kwargs: Any) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("db is down")
        if calls >= 3:
            third_call.set()
        return 1

    monkeypatch.setattr(scheduler, "run_due_checks", flaky)
    settings = Settings(scheduler_tick_seconds=0.001)

    async with httpx.AsyncClient() as client:
        task = asyncio.create_task(
            scheduler.run_scheduler(None, client, settings)  # type: ignore[arg-type]
        )
        await asyncio.wait_for(third_call.wait(), timeout=2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert calls >= 3
