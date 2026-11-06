import numpy as np
import pytest

from groundtruth.engine.matching.embedding_similarity import (
    FoundationModelEmbedder,
    NoEmbedder,
    rank_donors_by_embedding,
)

CANDS = {"a": np.array([1.0, 0.0]), "b": np.array([1.0, 1.0]), "c": np.array([-1.0, 0.0])}


def test_ranking_topk_and_gate() -> None:
    t = np.array([1.0, 0.0])
    assert [d.unit_id for d in rank_donors_by_embedding(t, CANDS)] == ["a", "b", "c"]
    assert [d.unit_id for d in rank_donors_by_embedding(t, CANDS, top_k=2)] == ["a", "b"]
    got = rank_donors_by_embedding(t, CANDS, min_similarity=0.5)
    assert [d.unit_id for d in got] == ["a", "b"]
    assert got[1].similarity == pytest.approx(2**-0.5)


def test_bad_inputs() -> None:
    with pytest.raises(ValueError):
        rank_donors_by_embedding(np.zeros(2), CANDS)
    with pytest.raises(ValueError):
        rank_donors_by_embedding(np.ones(3), CANDS)


def test_embedders_refuse_to_fake() -> None:
    with pytest.raises(NotImplementedError):
        NoEmbedder().embed(["x"])
    with pytest.raises(NotImplementedError, match="Embedder protocol"):
        FoundationModelEmbedder("clay").embed(["x"])
