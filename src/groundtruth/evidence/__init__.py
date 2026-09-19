"""Evidence assembly: the final deterministic stage before reporting."""

from groundtruth.evidence.assembler import (
    DIVERGENCE_THRESHOLD,
    AssemblyInputs,
    assemble_evidence,
    decide_verdict,
)

__all__ = ["DIVERGENCE_THRESHOLD", "AssemblyInputs", "assemble_evidence", "decide_verdict"]
