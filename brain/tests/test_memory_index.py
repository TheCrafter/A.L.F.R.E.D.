from alfred_brain.memory.index import VectorIndex


class FakeEmbedder:
    """Deterministic, offline: vector = per-word counts over a tiny vocab,
    so cosine similarity tracks word overlap."""
    VOCAB = ["alpha", "beta", "gamma", "delta"]

    def embed(self, texts):
        out = []
        for t in texts:
            tl = t.lower()
            out.append([float(tl.count(w)) for w in self.VOCAB])
        return out


def test_search_ranks_by_similarity():
    idx = VectorIndex(FakeEmbedder())
    idx.add("a", "alpha alpha")
    idx.add("b", "beta")
    idx.add("c", "gamma delta")
    hits = idx.search("alpha", k=2)
    assert hits[0][0] == "a"            # most similar to "alpha"
    assert len(hits) == 2
    assert all(isinstance(score, float) for _, score in hits)


def test_empty_index_returns_nothing():
    assert VectorIndex(FakeEmbedder()).search("alpha", k=5) == []


def test_remove_drops_from_results():
    idx = VectorIndex(FakeEmbedder())
    idx.add("a", "alpha")
    assert idx.remove("a") is True
    assert idx.search("alpha", k=5) == []
    assert idx.remove("a") is False


def test_zero_vector_query_is_safe():
    idx = VectorIndex(FakeEmbedder())
    idx.add("a", "alpha")
    # query has no vocab words -> zero vector -> no crash, score 0
    assert idx.search("zzz", k=5)[0][0] == "a"
