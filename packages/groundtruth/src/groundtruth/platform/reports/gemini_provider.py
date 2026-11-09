"""Google Gemini REST API narrator.

Exported here for symmetry with :mod:`groundtruth.platform.reports.anthropic_provider`.
The canonical implementation lives in :mod:`groundtruth.platform.reports.providers`.
"""

from __future__ import annotations

from groundtruth.platform.reports.anthropic_provider import REPORT_SCHEMA, sections_to_markdown
from groundtruth.platform.reports.providers import GeminiNarrator

__all__ = ["REPORT_SCHEMA", "GeminiNarrator", "sections_to_markdown"]
