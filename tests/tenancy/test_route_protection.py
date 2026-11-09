"""Safety net: no route of the live app ships without an authorization dependency.

``test_route_isolation`` covers routes that carry a case/project/run/job id in the path. This
test covers the rest: every route that is not on the explicit public allowlist must depend on
one of the authorization dependencies, so a future route with no id in its path cannot be added
unprotected.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi.dependencies.models import Dependant

from groundtruth.platform.api.app import app

PUBLIC_EXACT = frozenset({"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})
PUBLIC_PREFIXES = ("/auth/", "/docs/", "/redoc/", "/static/")

SCOPED_PARAMS = ("{project_id}", "{case_id}", "{run_id}", "{job_id}", "{slug}")
"""A route with one of these in its path must have a project- or org-kind dependency."""


INLINE_SCOPED = frozenset(
    {
        ("GET", "/runs/{run_id}"),
        ("GET", "/jobs/{run_id}"),
        ("POST", "/jobs/{run_id}/cancel"),
        ("GET", "/jobs/{job_id}/events"),
    }
)
"""Run and job routes authorize inside the handler (``authorize_filed``: the project is only
known after the run is read). They must still require a session (``context``) here, and
``test_route_isolation`` proves the 404/403 behaviour of each, so an entry cannot be added to
this list without that coverage."""


def _kind(call: Any) -> str | None:
    """The authorization kind a dependency declares with its ``__gt_authz__`` marker.

    A marker, not a name: a decoy closure called ``dependency`` inside a function called
    ``require_project`` has the same qualname as the real one but no marker.
    """
    kind = getattr(call, "__gt_authz__", None)
    return kind if isinstance(kind, str) else None


def _walk(routes: Any, prefix: str = "") -> Iterator[tuple[Any, str]]:
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _walk(original.routes, prefix + route.include_context.prefix)
        elif hasattr(route, "methods") and hasattr(route, "path"):
            yield route, prefix + route.path


def _calls(dependant: Dependant) -> Iterator[Any]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _calls(sub)


def _is_public(path: str) -> bool:
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES)


def _kinds(route: Any) -> set[str]:
    dependant = getattr(route, "dependant", None)  # a plain Starlette route has none
    if dependant is None:
        return set()
    return {k for call in _calls(dependant) if (k := _kind(call)) is not None}


def test_every_non_public_route_has_an_authorization_dependency() -> None:
    routes = list(_walk(app.routes))
    assert len(routes) > 30  # the enumeration actually found the app
    unprotected: set[tuple[str, str]] = set()
    for route, path in routes:
        if _is_public(path):
            continue
        kinds = _kinds(route)
        needs_scope = any(p in path for p in SCOPED_PARAMS)
        methods = route.methods - {"HEAD", "OPTIONS"}
        if needs_scope and all((m, path) in INLINE_SCOPED for m in methods):
            ok = "context" in kinds
        else:
            ok = bool(kinds & {"project", "org"}) if needs_scope else bool(kinds)
        if not ok:
            unprotected |= {(m, path) for m in route.methods - {"HEAD", "OPTIONS"}}
    assert not sorted(unprotected), (
        f"routes with no authorization dependency: {sorted(unprotected)}"
    )


def test_a_decoy_with_the_same_qualname_does_not_count() -> None:
    def require_project() -> Any:
        def dependency() -> None: ...

        return dependency

    decoy = require_project()
    decoy.__qualname__ = "require_project.<locals>.dependency"  # spoof the real name
    assert decoy.__qualname__ == "require_project.<locals>.dependency"
    assert _kind(decoy) is None
    from groundtruth.platform.auth.authz import Capability
    from groundtruth.platform.auth.authz import require_project as real

    assert _kind(real(Capability.OVERVIEW)) == "project"


def test_a_scoped_route_needs_a_project_or_org_dependency_not_just_a_session() -> None:
    from fastapi import APIRouter, Depends

    from groundtruth.platform.auth.authz import get_access_context

    router = APIRouter()

    @router.get("/projects/{project_id}/x", dependencies=[Depends(get_access_context)])
    def only_session(project_id: str) -> None: ...

    route = router.routes[0]
    assert _kinds(route) == {"context"}  # a session alone is not project authorization


def test_the_public_allowlist_is_minimal() -> None:
    """Every allowlisted path that exists is genuinely public: health, auth and API docs."""
    public = sorted({path for _r, path in _walk(app.routes) if _is_public(path)})
    assert "/health" in public
    assert all(p in PUBLIC_EXACT or p.startswith(PUBLIC_PREFIXES) for p in public)
