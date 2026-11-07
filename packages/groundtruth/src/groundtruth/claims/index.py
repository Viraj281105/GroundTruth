"""Dependency-free TF-IDF retriever over document chunks."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


def tokenize(text: str) -> list[str]:
    """Lower-case alphanumeric tokens."""
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Chunk:
    """A contiguous slice of a source document."""

    doc_id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Hit:
    """A retrieval result."""

    chunk: Chunk
    score: float


def chunk_text(text: str, doc_id: str, size: int = 600, overlap: int = 100) -> list[Chunk]:
    """Split ``text`` into overlapping character windows keeping offsets."""
    if size <= overlap:
        raise ValueError("size must exceed overlap")
    chunks: list[Chunk] = []
    pos = 0
    while pos < len(text):
        end = min(len(text), pos + size)
        chunks.append(Chunk(doc_id, pos, end, text[pos:end]))
        if end == len(text):
            break
        pos = end - overlap
    return chunks


class TfidfIndex:
    """In-memory TF-IDF index with cosine-similarity search."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = list(chunks)
        n = len(self.chunks)
        tfs = [Counter(tokenize(c.text)) for c in self.chunks]
        df: Counter[str] = Counter()
        for tf in tfs:
            df.update(tf.keys())
        self._idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}
        self._vecs = [self._vector(tf) for tf in tfs]

    def _vector(self, tf: Counter[str]) -> dict[str, float]:
        vec = {t: (1 + math.log(c)) * self._idf[t] for t, c in tf.items() if t in self._idf}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {t: v / norm for t, v in vec.items()} if norm else {}

    def search(self, query: str, k: int = 5) -> list[Hit]:
        """Return up to ``k`` chunks with positive cosine similarity, best first."""
        q = self._vector(Counter(tokenize(query)))
        scored = [
            Hit(chunk, sum(w * vec.get(t, 0.0) for t, w in q.items()))
            for chunk, vec in zip(self.chunks, self._vecs, strict=True)
        ]
        hits = [h for h in scored if h.score > 0]
        hits.sort(key=lambda h: -h.score)
        return hits[:k]
