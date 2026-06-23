from __future__ import annotations

import asyncio
from typing import Coroutine


class TurnManager:
    """Tracks in-flight agent-turn tasks so the global kill switch can cancel them."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, corr: str, coro: Coroutine) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks[corr] = task
        task.add_done_callback(lambda t: self._tasks.pop(corr, None))
        return task

    async def kill_all(self) -> int:
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    @property
    def active_count(self) -> int:
        return len(self._tasks)
