import asyncio


class EventBus:
    """Async pub/sub. Publishers fan a message out to every subscriber's queue.

    publish() is synchronous and non-blocking (put_nowait on unbounded queues) so
    it is safe to call from inside a cancellation handler without awaiting.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, message: dict) -> None:
        for q in list(self._subscribers):
            q.put_nowait(message)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
