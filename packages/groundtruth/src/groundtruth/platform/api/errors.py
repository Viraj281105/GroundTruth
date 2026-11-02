"""Errors specific to the stored-run endpoints, and how they map to HTTP.

The contract's ``ErrorCode`` describes how an *analysis* can fail, and ``ERROR_STATUS``
in ``app.py`` is tested to cover every member. These errors describe how *retrieving
stored runs* can fail, which is a platform matter and not part of the engine/platform
contract, so they live here and do not extend ``ErrorCode``.

They use the same body shape ``/verify`` already sends for engine failures,
``detail: {code, message, ...}``, so a client reads a ``code`` and never parses prose.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import HTTPException
from pydantic import BaseModel

from groundtruth.contracts.result import ErrorCode


class ApiErrorCode(StrEnum):
    RUN_NOT_FOUND = "run_not_found"
    INVALID_CURSOR = "invalid_cursor"
    INVALID_FILTER = "invalid_filter"
    STORE_NOT_CONFIGURED = "store_not_configured"
    """No database is set up for this process. Deployment configuration, not a bug."""
    STORE_UNAVAILABLE = "store_unavailable"
    """The database is configured but not answering."""
    STORE_ERROR = "store_error"
    """Stored data is inconsistent. A real fault; it needs an operator."""
    CONTRACT_VERSION_MISMATCH = ErrorCode.CONTRACT_VERSION_MISMATCH.value
    """A stored run was written under a contract this code cannot read. Same code and
    status the engine path uses for the same condition."""
    NOT_IMPLEMENTED = ErrorCode.NOT_IMPLEMENTED.value
    """Observed-data jobs cannot be queued yet. Same code and status as ``/verify``."""
    CASE_NOT_FOUND = "case_not_found"
    JOB_ALREADY_FINISHED = "job_already_finished"
    """The job succeeded or failed, so there is nothing left to cancel."""


API_ERROR_STATUS: dict[ApiErrorCode, int] = {
    ApiErrorCode.RUN_NOT_FOUND: 404,
    ApiErrorCode.INVALID_CURSOR: 400,
    ApiErrorCode.INVALID_FILTER: 422,
    ApiErrorCode.STORE_NOT_CONFIGURED: 503,
    ApiErrorCode.STORE_UNAVAILABLE: 503,
    ApiErrorCode.STORE_ERROR: 500,
    ApiErrorCode.CONTRACT_VERSION_MISMATCH: 409,
    ApiErrorCode.NOT_IMPLEMENTED: 501,
    ApiErrorCode.CASE_NOT_FOUND: 404,
    ApiErrorCode.JOB_ALREADY_FINISHED: 409,
}
"""Every member must appear here; a test enforces it."""


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    hint: str | None = None


class ApiErrorBody(BaseModel):
    """The JSON body of an error response, for the OpenAPI schema."""

    detail: ApiErrorDetail


def api_error(code: ApiErrorCode, message: str, hint: str | None = None) -> HTTPException:
    """An ``HTTPException`` carrying a structured body and the code's status."""
    return HTTPException(
        status_code=API_ERROR_STATUS[code],
        detail={"code": code.value, "message": message, "hint": hint},
    )
