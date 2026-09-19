"""Report generation: deterministic rendering and grounded GenAI narration.

**Owner: Bhumi.**
"""

from groundtruth.platform.reports.narrative import (
    Report,
    generate_report,
    render_deterministic,
)
from groundtruth.platform.reports.providers import EchoNarrator, Narrator, build_narrator

__all__ = [
    "EchoNarrator",
    "Narrator",
    "Report",
    "build_narrator",
    "generate_report",
    "render_deterministic",
]
