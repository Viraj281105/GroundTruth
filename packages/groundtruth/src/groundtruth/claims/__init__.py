"""Document claim extraction, retrieval and comparison (no LLM)."""

from groundtruth.claims.compare import Discrepancy, Severity, compare_claims
from groundtruth.claims.extract import Claim, ClaimKind, extract_claims
from groundtruth.claims.index import Chunk, Hit, TfidfIndex, chunk_text

__all__ = [
    "Chunk",
    "Claim",
    "ClaimKind",
    "Discrepancy",
    "Hit",
    "Severity",
    "TfidfIndex",
    "chunk_text",
    "compare_claims",
    "extract_claims",
]
