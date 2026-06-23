import os

import pytest

from alfred_brain.memory import VaultMemory
from alfred_brain.memory.index import FastEmbedEmbedder

pytestmark = pytest.mark.skipif(
    not os.getenv("ALFRED_TEST_FASTEMBED"),
    reason="set ALFRED_TEST_FASTEMBED=1 to run the real fastembed smoke (downloads a model)",
)


def test_real_fastembed_remember_and_recall(tmp_path):
    mem = VaultMemory(tmp_path / "vault", FastEmbedEmbedder())
    mem.remember("The user's favorite language is Python", type="preference")
    mem.remember("The capital of France is Paris", type="fact")
    hits = mem.recall("what programming language does the user like", k=1)
    assert hits and "Python" in hits[0].text
