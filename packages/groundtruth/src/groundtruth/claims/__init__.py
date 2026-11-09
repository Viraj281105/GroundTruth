"""Document claim extraction, retrieval and comparison (no LLM)."""

from groundtruth.claims.compare import Discrepancy, Severity, compare_claims
from groundtruth.claims.extract import Claim, ClaimKind, extract_claims
from groundtruth.claims.index import Chunk, Hit, TfidfIndex, chunk_text
from groundtruth.claims.verification_engine import (
    ClaimVerificationPortfolio,
    ConfidenceGrading,
    DecomposedStatement,
    Grade,
    StructuredClaimKind,
    StructuredClaimVerification,
    VerificationStatus,
    calculate_evidence_grades,
    score_to_grade,
    verify_project_claims,
)

__all__ = [
    "Chunk",
    "Claim",
    "ClaimKind",
    "ClaimVerificationPortfolio",
    "ConfidenceGrading",
    "DecomposedStatement",
    "Discrepancy",
    "Grade",
    "Hit",
    "Severity",
    "StructuredClaimKind",
    "StructuredClaimVerification",
    "TfidfIndex",
    "VerificationStatus",
    "calculate_evidence_grades",
    "chunk_text",
    "compare_claims",
    "extract_claims",
    "score_to_grade",
    "verify_project_claims",
]
