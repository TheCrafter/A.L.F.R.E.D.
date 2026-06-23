from alfred_brain.events import EventBus


async def test_publish_fans_out_to_all_subscribers():
    bus = EventBus()
    a = bus.subscribe()
    b = bus.subscribe()
    bus.publish({"type": "x"})
    assert a.get_nowait() == {"type": "x"}
    assert b.get_nowait() == {"type": "x"}


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    a = bus.subscribe()
    bus.unsubscribe(a)
    bus.publish({"type": "y"})
    assert a.empty()
    assert bus.subscriber_count == 0


async def test_publish_with_no_subscribers_is_noop():
    bus = EventBus()
    bus.publish({"type": "z"})  # must not raise
