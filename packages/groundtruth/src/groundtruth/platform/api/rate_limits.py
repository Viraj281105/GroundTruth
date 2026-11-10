"""A per-user budget for analysis submissions (#51).

**Owner: Bhumi.** Every analysis costs a worker minutes, so one account must not be able to
fill the queue. ``POST /jobs`` and ``POST /cases/{id}/verify`` share one budget per user:
``ANALYSIS_RATE_LIMIT`` submissions in ``ANALYSIS_RATE_WINDOW_SECONDS`` (20 in 10 minutes by
default). A submission answered from a stored result still counts: the caller cannot know in
advance which one will be, and a simple rule is one a user can predict.

This reuses Viraj's sliding-window :class:`~groundtruth.platform.auth.ratelimit.FailureLimiter`
unchanged. It counts "events in a window"; here an event is an accepted submission rather than
a failed sign-in. Like the login limiter it lives in one process's memory, so with N API
processes the effective limit is N times the setting (today there is one; see SECURITY.md).

Over the limit is a ``429 too_many_submissions`` with ``Retry-After``. It is not a scientific
refusal (``is_refusal`` is false), it is audited as a denied ``run.start``, and it is counted
in ``gt_submissions_rate_limited_total``.
"""

from __future__ import annotations

import threading

from fastapi import HTTPException, Request

from groundtruth.platform.api.errors import API_ERROR_STATUS, ApiErrorCode
from groundtruth.platform.audit.service import record_event
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.auth.ratelimit import FailureLimiter
from groundtruth.platform.config import get_settings
from groundtruth.platform.metrics import record_rate_limited

_SCOPE = "analysis-submission"
_lock = threading.Lock()
_limiters: dict[tuple[int, int], FailureLimiter] = {}


def submission_limiter() -> FailureLimiter:
    """The limiter for the configured budget. A changed setting gets a fresh window."""
    settings = get_settings()
    key = (settings.analysis_rate_limit, settings.analysis_rate_window_seconds)
    with _lock:
        limiter = _limiters.get(key)
        if limiter is None:
            limiter = _limiters[key] = FailureLimiter(max_failures=key[0], window=key[1])
        return limiter


def reset_submission_limits() -> None:
    """Forget every count. For tests."""
    with _lock:
        for limiter in _limiters.values():
            limiter.clear()


def spend_submission(
    request: Request,
    *,
    user_id: str | None,
    organization_id: str | None,
    path: str,
    case_id: str,
) -> None:
    """Count one submission against the caller's budget, or refuse it with a 429.

    Call it once the submission is valid and about to be accepted, so a rejected request does
    not use up the budget.
    """
    if user_id is None:  # every analysis route requires a session; nothing to key on otherwise
        return
    limiter = submission_limiter()
    key = (user_id, _SCOPE)
    wait = limiter.retry_after(key)
    if wait is None:
        limiter.record_failure(key)  # the limiter's name for "count one event in the window"
        return
    record_rate_limited(path)
    with resolve_sessions(request)() as db:
        record_event(
            db,
            action="run.start",
            outcome="denied",
            actor_user_id=user_id,
            organization_id=organization_id,
            resource_type="case",
            resource_id=case_id,
            request=request,
            details={"reason": "rate_limited", "path": path},
        )
        db.commit()
    settings = get_settings()
    raise HTTPException(
        status_code=API_ERROR_STATUS[ApiErrorCode.TOO_MANY_SUBMISSIONS],
        detail={
            "code": ApiErrorCode.TOO_MANY_SUBMISSIONS.value,
            "message": (
                f"You have submitted {settings.analysis_rate_limit} analyses in the last "
                f"{settings.analysis_rate_window_seconds // 60} minutes, the most allowed."
            ),
            "hint": f"Try again in {wait} seconds. Results you already have stay available.",
        },
        headers={"Retry-After": str(wait)},
    )


__all__ = ["reset_submission_limits", "spend_submission", "submission_limiter"]
