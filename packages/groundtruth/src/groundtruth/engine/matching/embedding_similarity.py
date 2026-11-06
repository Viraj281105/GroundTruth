"""Donor similarity from precomputed embedding vectors.

Embeddings are never fabricated: callers supply vectors, or plug in a real
:class:`Embedder`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


class Embedder(Protocol):
    """Turns a location/imagery reference into an embedding vector."""

    def embed(self, refs: Sequence[Any]) -> np.ndarray:
        """Return an ``(n, d)`` array, one row per reference."""
        ...


class NoEmbedder:
    """Default: no model. Vectors must be supplied by the user."""

    def embed(self, refs: Sequence[Any]) -> np.ndarray:
        raise NotImplementedError(
            "No embedder configured. Supply precomputed vectors to rank_donors_by_embedding, "
            "or pass an Embedder implementation."
        )


class FoundationModelEmbedder:
    """Stub for Prithvi / Clay adapters. Does not produce embeddings."""

    def __init__(self, model: str = "prithvi") -> None:
        self.model = model

    def embed(self, refs: Sequence[Any]) -> np.ndarray:
        raise NotImplementedError(
            f"The {self.model!r} adapter is not implemented. To use it: install the model's "
            "package and weights (torch/transformers for Prithvi, claymodel for Clay), run it "
            "over your imagery chips offline, then pass the resulting vectors to "
            "rank_donors_by_embedding. Or implement the Embedder protocol."
        )


@dataclass(frozen=True)
class SimilarDonor:
    unit_id: str
    similarity: float


def cosine_similarity(target: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a ``(d,)`` vector and each row of ``(n, d)``."""
    t = np.asarray(target, dtype=float)
    m = np.asarray(matrix, dtype=float)
    if t.ndim != 1 or m.ndim != 2 or m.shape[1] != t.shape[0]:
        raise ValueError(f"Shape mismatch: target {t.shape}, candidates {m.shape}.")
    if not (np.isfinite(t).all() and np.isfinite(m).all()):
        raise ValueError("Embeddings must be finite.")
    tn = np.linalg.norm(t)
    mn = np.linalg.norm(m, axis=1)
    if tn == 0.0 or (mn == 0.0).any():
        raise ValueError("Zero-norm embedding: cosine similarity is undefined.")
    return np.asarray((m @ t) / (mn * tn))


def rank_donors_by_embedding(
    target_vector: np.ndarray,
    candidate_vectors: Mapping[str, np.ndarray],
    *,
    top_k: int | None = None,
    min_similarity: float | None = None,
) -> list[SimilarDonor]:
    """Rank candidates by cosine similarity, descending; ties broken by unit id.

    Candidates below ``min_similarity`` are dropped, then ``top_k`` are kept.
    """
    if top_k is not None and top_k < 1:
        raise ValueError("top_k must be >= 1.")
    if not candidate_vectors:
        return []
    ids = sorted(candidate_vectors)
    sims = cosine_similarity(target_vector, np.vstack([candidate_vectors[i] for i in ids]))
    ranked = sorted(zip(ids, sims.tolist(), strict=True), key=lambda p: (-p[1], p[0]))
    if min_similarity is not None:
        ranked = [p for p in ranked if p[1] >= min_similarity]
    if top_k is not None:
        ranked = ranked[:top_k]
    return [SimilarDonor(u, s) for u, s in ranked]
