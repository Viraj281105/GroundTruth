"""Structural alignment of observed series to the analysis window.

The estimators index arrays by position: row ``n_pre`` is the first
post-treatment period. That is only true if every series carries exactly the
window's periods, in order, with nothing missing. A provider returning real
imagery cannot promise that — a series may start late, skip a cloud-starved
year, or differ in length between donors — and positional indexing would then
fit happily against the wrong treatment date.

This module turns that assumption into a check. It derives the pre/post split
from period *labels*, refuses any series that does not cover the window, and
builds the panel the estimators consume only from validated series.

What to do *about* a sparse period (down-weight, exclude, refuse) is a
methodological question owned by issue #9. This module only guarantees that
whatever arrives is aligned before it reaches an estimator, and that a
misaligned series produces a refusal rather than a number.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from groundtruth.contracts.errors import InsufficientDataError
from groundtruth.contracts.request import AnalysisWindow
from groundtruth.contracts.types import TimeSeries


def analysis_periods(window: AnalysisWindow) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The pre- and post-treatment period labels a series must cover.

    Periods strictly between ``pre_end`` and ``post_start`` belong to neither
    side. The contract allows such a gap so a transition year can be left out
    of both the fit and the effect; positional indexing would silently have
    counted it as post-treatment.
    """
    pre = tuple(range(window.pre_start, window.pre_end + 1))
    post = tuple(range(window.post_start, window.post_end + 1))
    return pre, post


@dataclass(frozen=True)
class SeriesDefect:
    """Why one unit's series cannot be aligned to the window."""

    unit_id: str
    missing_periods: tuple[int, ...] = ()
    non_finite_periods: tuple[int, ...] = ()

    def describe(self) -> str:
        """One human-readable clause naming the unit and its gaps."""
        parts = []
        if self.missing_periods:
            parts.append(f"missing periods {list(self.missing_periods)}")
        if self.non_finite_periods:
            parts.append(f"non-finite values in periods {list(self.non_finite_periods)}")
        return f"{self.unit_id}: " + ", ".join(parts)

    def as_detail(self) -> dict[str, object]:
        """JSON-safe form for ``AnalysisError.detail``."""
        return {
            "unit_id": self.unit_id,
            "missing_periods": list(self.missing_periods),
            "non_finite_periods": list(self.non_finite_periods),
        }


class MisalignedSeriesError(InsufficientDataError):
    """One or more series do not cover the analysis window.

    Subclasses :class:`InsufficientDataError` so callers that already map that
    error to ``ErrorCode.INSUFFICIENT_DATA`` refuse correctly, while carrying
    the per-unit defects for the refusal's ``detail``.
    """

    def __init__(self, defects: Sequence[SeriesDefect], window: AnalysisWindow) -> None:
        self.defects = tuple(defects)
        self.window = window
        shown = "; ".join(d.describe() for d in self.defects[:5])
        more = f"; and {len(self.defects) - 5} more" if len(self.defects) > 5 else ""
        super().__init__(
            f"{len(self.defects)} observed series do not cover the analysis window "
            f"{window.pre_start}-{window.post_end}: {shown}{more}"
        )

    def as_detail(self) -> dict[str, object]:
        """JSON-safe form for ``AnalysisError.detail``."""
        return {
            "window": {
                "pre_start": self.window.pre_start,
                "pre_end": self.window.pre_end,
                "post_start": self.window.post_start,
                "post_end": self.window.post_end,
            },
            "n_units_misaligned": len(self.defects),
            "units": [d.as_detail() for d in self.defects],
        }


def _defect(series: TimeSeries, required: tuple[int, ...]) -> SeriesDefect | None:
    by_period = dict(zip(series.periods, series.values, strict=True))
    missing = tuple(p for p in required if p not in by_period)
    non_finite = tuple(p for p in required if p in by_period and not math.isfinite(by_period[p]))
    if missing or non_finite:
        return SeriesDefect(series.unit_id, missing, non_finite)
    return None


def _select(series: TimeSeries, periods: tuple[int, ...]) -> np.ndarray:
    by_period = dict(zip(series.periods, series.values, strict=True))
    return np.asarray([by_period[p] for p in periods], dtype=float)


@dataclass(frozen=True)
class AlignedPanel:
    """Treated and donor series on identical, validated period labels.

    Rows are periods in ``pre_periods + post_periods`` order, so
    ``n_pre`` is derived from labels and is guaranteed to point at
    ``window.post_start``.
    """

    pre_periods: tuple[int, ...]
    post_periods: tuple[int, ...]
    treated: np.ndarray
    donors: np.ndarray
    donor_ids: tuple[str, ...]
    dropped_periods: tuple[int, ...] = field(default=())

    @property
    def periods(self) -> tuple[int, ...]:
        """Every period the estimators see, in row order."""
        return self.pre_periods + self.post_periods

    @property
    def n_pre(self) -> int:
        """Row index of the first post-treatment period."""
        return len(self.pre_periods)


def align_panel(
    window: AnalysisWindow,
    project: TimeSeries,
    donors: Mapping[str, TimeSeries],
    donor_ids: Sequence[str],
) -> AlignedPanel:
    """Validate every series against the window and build the estimator panel.

    Args:
        window: The requested analysis window.
        project: The treated unit's observed series.
        donors: Observed series keyed by donor unit id.
        donor_ids: Donors to include, in column order.

    Returns:
        An :class:`AlignedPanel` whose rows are exactly the window's pre and
        post periods. Periods the provider returned outside the window, or in a
        gap between ``pre_end`` and ``post_start``, are dropped and recorded.

    Raises:
        MisalignedSeriesError: if any series is missing a required period or
            carries a non-finite value in one. Every offending unit is
            reported, not just the first.
    """
    pre, post = analysis_periods(window)
    required = pre + post
    included = [project, *(donors[uid] for uid in donor_ids)]

    defects = [d for s in included if (d := _defect(s, required)) is not None]
    if defects:
        raise MisalignedSeriesError(defects, window)

    required_set = set(required)
    dropped = sorted({p for s in included for p in s.periods if p not in required_set})

    donor_matrix = (
        np.column_stack([_select(donors[uid], required) for uid in donor_ids])
        if donor_ids
        else np.empty((len(required), 0))
    )
    return AlignedPanel(
        pre_periods=pre,
        post_periods=post,
        treated=_select(project, required),
        donors=donor_matrix,
        donor_ids=tuple(donor_ids),
        dropped_periods=tuple(dropped),
    )


__all__ = [
    "AlignedPanel",
    "MisalignedSeriesError",
    "SeriesDefect",
    "align_panel",
    "analysis_periods",
]
