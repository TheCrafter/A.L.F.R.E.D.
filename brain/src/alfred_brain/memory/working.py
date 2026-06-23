from __future__ import annotations

from collections import deque
from typing import Literal

from ..providers.base import TurnMessage


class WorkingMemory:
    """In-RAM rolling buffer of recent user/assistant messages (short-term memory).

    The most recent `window` messages are the conversation context fed to the
    model. Messages aging out of the window accumulate in `pending` and are handed
    to extraction in batches of `window // 2`.
    """

    def __init__(self, window: int = 20) -> None:
        self._window = max(2, window)
        self._recent: deque[TurnMessage] = deque()
        self._pending: list[TurnMessage] = []

    @property
    def _batch_size(self) -> int:
        return max(1, self._window // 2)

    def append(self, role: Literal["user", "assistant"], text: str) -> None:
        self._recent.append(TurnMessage(role=role, content=text))
        self._evict()

    def _evict(self) -> None:
        while len(self._recent) > self._window:
            self._pending.append(self._recent.popleft())

    def context(self) -> list[TurnMessage]:
        return list(self._recent)

    def take_batch(self) -> list[TurnMessage]:
        if len(self._pending) < self._batch_size:
            return []
        batch = self._pending
        self._pending = []
        return batch

    def drain(self) -> list[TurnMessage]:
        batch = self._pending + list(self._recent)
        self._pending = []
        self._recent.clear()
        return batch

    def set_window(self, n: int) -> None:
        self._window = max(2, n)
        self._evict()
