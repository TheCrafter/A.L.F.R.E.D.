from __future__ import annotations

from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Local CPU embeddings via fastembed (ONNX).

    The model is loaded lazily on the FIRST embed() call, never in __init__ — so
    constructing the brain (create_app) with an empty vault does no model load or
    download. This keeps the test suite fast/offline (empty index -> no embed).
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_name = model_name
        self._model: object | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return [v.tolist() for v in self._model.embed(texts)]


def _cosine(q: np.ndarray, m: np.ndarray) -> np.ndarray:
    qn = np.linalg.norm(q)
    mn = np.linalg.norm(m, axis=1)
    denom = mn * qn
    sims = np.zeros(m.shape[0], dtype=float)
    nz = denom > 0
    sims[nz] = (m[nz] @ q) / denom[nz]
    return sims


class VectorIndex:
    """In-memory vector store. Rebuilt from the vault at startup."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, id: str, text: str) -> None:
        self._ids.append(id)
        self._vectors.append(self._embedder.embed([text])[0])

    def remove(self, id: str) -> bool:
        try:
            i = self._ids.index(id)
        except ValueError:
            return False
        self._ids.pop(i)
        self._vectors.pop(i)
        return True

    def clear(self) -> None:
        self._ids.clear()
        self._vectors.clear()

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        if not self._ids:
            return []
        q = np.asarray(self._embedder.embed([query])[0], dtype=float)
        m = np.asarray(self._vectors, dtype=float)
        sims = _cosine(q, m)
        order = np.argsort(-sims)[:k]
        return [(self._ids[i], float(sims[i])) for i in order]
