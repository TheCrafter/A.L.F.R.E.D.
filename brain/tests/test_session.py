import asyncio

from alfred_brain.session import TurnManager


async def test_start_tracks_and_autoremoves():
    tm = TurnManager()

    async def quick():
        return None

    task = tm.start("c1", quick())
    await task
    await asyncio.sleep(0)  # let done-callback run
    assert tm.active_count == 0


async def test_kill_all_cancels_running_turns():
    tm = TurnManager()
    started = asyncio.Event()

    async def forever():
        started.set()
        await asyncio.Event().wait()

    tm.start("c1", forever())
    await started.wait()
    assert tm.active_count == 1
    killed = await tm.kill_all()
    assert killed == 1
    assert tm.active_count == 0


async def test_kill_all_with_none_active_returns_zero():
    assert await TurnManager().kill_all() == 0
