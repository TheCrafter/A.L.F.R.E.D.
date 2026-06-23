from alfred_brain.memory.working import WorkingMemory


def test_context_returns_recent_within_window():
    wm = WorkingMemory(window=4)
    for i in range(3):
        wm.append("user", f"u{i}")
    ctx = wm.context()
    assert [m.content for m in ctx] == ["u0", "u1", "u2"]
    assert all(m.role == "user" for m in ctx)


def test_overflow_moves_to_pending_and_batches():
    wm = WorkingMemory(window=4)  # batch_size = 2
    # 4 fit in the window; the 5th and 6th evict u0, u1 into pending
    for i in range(6):
        wm.append("user", f"u{i}")
    assert [m.content for m in wm.context()] == ["u2", "u3", "u4", "u5"]
    batch = wm.take_batch()
    assert [m.content for m in batch] == ["u0", "u1"]
    assert wm.take_batch() == []  # cleared


def test_take_batch_empty_below_batch_size():
    wm = WorkingMemory(window=4)  # batch_size = 2
    for i in range(5):  # one eviction -> pending has 1 < 2
        wm.append("user", f"u{i}")
    assert wm.take_batch() == []


def test_drain_returns_pending_plus_window_and_clears():
    wm = WorkingMemory(window=4)
    for i in range(6):
        wm.append("user", f"u{i}")
    drained = wm.drain()
    assert [m.content for m in drained] == ["u0", "u1", "u2", "u3", "u4", "u5"]
    assert wm.context() == [] and wm.take_batch() == []


def test_set_window_shrinks_into_pending():
    wm = WorkingMemory(window=10)
    for i in range(6):
        wm.append("user", f"u{i}")
    wm.set_window(2)
    assert [m.content for m in wm.context()] == ["u4", "u5"]
    # pending now has u0..u3 (4 >= batch_size 1) -> one batch available
    assert [m.content for m in wm.take_batch()] == ["u0", "u1", "u2", "u3"]
