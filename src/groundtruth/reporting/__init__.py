"""Reporting layer. The only place a language model is permitted to run."""

from groundtruth.reporting.grounding import (
    GroundingPolicy,
    GroundingReport,
    enforce_grounding,
    policy_for_bundle,
    verify_grounding,
)
from groundtruth.reporting.narrative import Report, generate_report, render_deterministic
from groundtruth.reporting.providers import EchoNarrator, Narrator, build_narrator

__all__ = [
    "EchoNarrator",
    "GroundingPolicy",
    "GroundingReport",
    "Narrator",
    "Report",
    "build_narrator",
    "enforce_grounding",
    "generate_report",
    "policy_for_bundle",
    "render_deterministic",
    "verify_grounding",
]
