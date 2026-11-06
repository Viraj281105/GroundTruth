"""Which browser origins may call the API (issue #40).

The frontend is deployed separately from the API, so the browser sends a CORS preflight
before every cross-origin call. The allowed origins come from ``CORS_ALLOWED_ORIGINS``
(falling back to ``FRONTEND_URL``) and are always an explicit list: a wildcard would let
any site drive the API from a visitor's browser.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

from groundtruth.platform.api.app import app
from groundtruth.platform.config import Settings, get_settings


def _settings(**values: str) -> Settings:
    # _env_file=None: the developer's own .env must not decide what these tests see.
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


class TestSettings:
    @pytest.fixture(autouse=True)
    def _clean_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        monkeypatch.delenv("FRONTEND_URL", raising=False)

    def test_unset_means_the_frontend_url_alone(self) -> None:
        settings = _settings(frontend_url="https://app.example.org")
        assert settings.cors_origins == ["https://app.example.org"]

    def test_blank_means_unset(self) -> None:
        # `CORS_ALLOWED_ORIGINS=` in an env file is how .env.example ships it.
        settings = _settings(cors_allowed_origins="  ", frontend_url="http://localhost:3000")
        assert settings.cors_origins == ["http://localhost:3000"]

    def test_several_origins_trimmed_deduplicated_in_order(self) -> None:
        settings = _settings(
            cors_allowed_origins=" https://a.example.org/ , http://localhost:3000,,"
            "https://a.example.org"
        )
        assert settings.cors_origins == ["https://a.example.org", "http://localhost:3000"]

    def test_the_list_replaces_the_frontend_url_rather_than_adding_to_it(self) -> None:
        settings = _settings(
            cors_allowed_origins="https://a.example.org", frontend_url="http://localhost:3000"
        )
        assert settings.cors_origins == ["https://a.example.org"]

    @pytest.mark.parametrize("value", ["*", "https://a.example.org, *", " * "])
    def test_a_wildcard_is_refused(self, value: str) -> None:
        with pytest.raises(ValidationError, match="never"):
            _settings(cors_allowed_origins=value)

    def test_read_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.example.org,https://b.example.org")
        assert _settings().cors_origins == ["https://a.example.org", "https://b.example.org"]


class TestMiddleware:
    def test_the_app_allows_exactly_the_configured_origins(self) -> None:
        [cors] = [m for m in app.user_middleware if m.cls is CORSMiddleware]
        assert cors.kwargs["allow_origins"] == get_settings().cors_origins
        assert "*" not in cors.kwargs["allow_origins"]
        assert (
            cors.kwargs["allow_credentials"] is True
        )  # cookie auth (docs/security/auth.md); origins stay exact

    def _preflight(self, origin: str, method: str = "POST") -> tuple[int, dict[str, str]]:
        with TestClient(app) as client:
            response = client.options(
                "/jobs",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "content-type",
                },
            )
        return response.status_code, dict(response.headers)

    def test_a_configured_origin_may_submit_a_job(self) -> None:
        origin = get_settings().cors_origins[0]
        status, headers = self._preflight(origin)
        assert status == 200
        assert headers["access-control-allow-origin"] == origin  # echoed, never "*"
        assert "POST" in headers["access-control-allow-methods"]

    def test_any_other_origin_is_refused(self) -> None:
        status, headers = self._preflight("https://not-ours.example.net")
        assert status == 400
        assert "access-control-allow-origin" not in headers

    def test_a_simple_request_from_another_origin_gets_no_allow_header(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health", headers={"Origin": "https://not-ours.example.net"})
        # The server still answers; the browser withholds the body from the page.
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers
