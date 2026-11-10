"""The Earth Engine observation service (#22), without a network.

A fake backend stands in for Earth Engine, so these tests pin down everything the
platform owns — credentials, retries, rate limiting, caching, pinning, and the
mapping to a ``TimeSeries`` — and leave the Earth Engine graph itself to the
network tests in ``test_earthengine_network.py``.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import pathlib
import traceback
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from pydantic import SecretStr

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.contracts.ports import ObservationAccess, ObservationSpec
from groundtruth.contracts.request import AnalysisRequest, AnalysisWindow, ClaimUnderTest, UnitRef
from groundtruth.contracts.types import Indicator
from groundtruth.engine import describe_engine
from groundtruth.platform.config import Settings
from groundtruth.platform.datasets import catalog
from groundtruth.platform.datasets.access import earth_engine_access, earth_engine_observations
from groundtruth.platform.datasets.cache import ReductionCache
from groundtruth.platform.datasets.catalog import (
    AGREED_SENSORS,
    SNAPSHOT_DATE,
    SNAPSHOT_MICROS,
    pinned_dataset,
)
from groundtruth.platform.datasets.earthengine import (
    ServiceAccountKey,
    YearQuery,
    classify,
    load_service_account_key,
)
from groundtruth.platform.datasets.observation import (
    EarthEngineObservationAccess,
    histogram_median,
    scene_fingerprint,
)
from groundtruth.platform.datasets.resilience import (
    PermanentError,
    RateLimiter,
    RetryPolicy,
    TransientError,
    call_with_retry,
)

SRC = pathlib.Path(__file__).resolve().parents[1] / "packages/groundtruth/src/groundtruth"

# Every secret part of the fake key carries a marker no legitimate message contains.
PRIVATE_KEY_BODY = "SENTINELPRIVATEKEYBODYabcdefghijklmnop0123456789"
PRIVATE_KEY = f"-----BEGIN PRIVATE KEY-----\n{PRIVATE_KEY_BODY}\n-----END PRIVATE KEY-----\n"
KEY_INFO = {
    "type": "service_account",
    "project_id": "gt-test-project",
    "private_key_id": "SENTINELKEYID0123456789",
    "private_key": PRIVATE_KEY,
    "client_email": "sentinel-account@gt-test-project.iam.gserviceaccount.com",
    "client_id": "SENTINELCLIENTID987654321",
}
KEY_JSON = json.dumps(KEY_INFO)
SECRETS = (
    PRIVATE_KEY_BODY,
    "SENTINELKEYID0123456789",
    "SENTINELCLIENTID987654321",
    "sentinel-account@",
)

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[28.0, -17.0], [28.1, -17.0], [28.1, -16.9], [28.0, -16.9], [28.0, -17.0]]],
}


def ee_error(message: str) -> Exception:
    """An exception shaped like ``ee.ee_exception.EEException``."""
    return type("EEException", (Exception,), {})(message)


class HttpError(Exception):
    """Shaped like ``googleapiclient.errors.HttpError``: the status is on ``resp``."""

    def __init__(self, status: int, message: str = "http error") -> None:
        super().__init__(message)
        self.resp = type("Resp", (), {"status": status})()


class FakeBackend:
    """Earth Engine as scripted data. Records every call it receives."""

    def __init__(
        self,
        *,
        years: dict[int, dict[str, Any]] | None = None,
        failures: dict[str, list[BaseException]] | None = None,
    ) -> None:
        self.years = years or {}
        self.failures = {k: list(v) for k, v in (failures or {}).items()}
        self.calls: list[tuple[str, Any]] = []

    def _maybe_fail(self, method: str) -> None:
        queue = self.failures.get(method)
        if queue:
            raise queue.pop(0)

    def initialize(self, key: ServiceAccountKey, project: str) -> None:
        self.calls.append(("initialize", project))
        self._maybe_fail("initialize")

    def _year(self, query: YearQuery) -> dict[str, Any]:
        return self.years.get(query.year, default_year(query.year))

    def list_scenes(self, query: YearQuery) -> dict[str, Any]:
        self.calls.append(("list_scenes", query))
        self._maybe_fail("list_scenes")
        year = self._year(query)
        return {
            "n_available": year.get("n_available", len(year["ids"])),
            "ids": year["ids"],
            "versions": year["versions"],
        }

    def reduce(self, query: YearQuery) -> dict[str, Any]:
        self.calls.append(("reduce", query))
        self._maybe_fail("reduce")
        year = self._year(query)
        return {"mean": {"index": year["mean"]}, "histogram": {"count": year["histogram"]}}

    def count(self, method: str) -> int:
        return sum(1 for name, _ in self.calls if name == method)


def default_year(year: int) -> dict[str, Any]:
    n = 10 + year % 7
    return {
        "ids": [f"LE07_170072_{year}{i:04d}" for i in range(n)],
        "versions": [1_700_000_000_000_000 + i for i in range(n)],
        "mean": 0.40 + (year - 2000) / 1000,
        # 60 pixels: 10 never clear, then counts 3..7; median of 60 values averages two.
        "histogram": {"0": 10, "3.0": 10, "4": 10, "5": 15, "6": 10, "7": 5},
    }


def make_service(
    backend: FakeBackend | None = None,
    *,
    credentials: str | None = KEY_JSON,
    cache_dir: pathlib.Path | None = None,
    sleeps: list[float] | None = None,
    **kwargs: Any,
) -> EarthEngineObservationAccess:
    record = sleeps if sleeps is not None else []
    return EarthEngineObservationAccess(
        sensor=kwargs.pop("sensor", "landsat7"),
        credentials=SecretStr(credentials) if credentials is not None else None,
        cache=ReductionCache(cache_dir) if cache_dir is not None else None,
        backend=backend or FakeBackend(),
        sleep=record.append,
        now=lambda: datetime(2026, 11, 3, 12, 0, tzinfo=UTC),
        **kwargs,
    )


def kariba_spec(geometry: dict[str, Any] | None = SQUARE, **overrides: Any) -> ObservationSpec:
    fields: dict[str, Any] = {
        "unit": UnitRef(unit_id="kariba-redd", geometry=geometry),
        "indicator": Indicator.NDVI,
        "start_period": 2001,
        "end_period": 2022,
    }
    fields.update(overrides)
    return ObservationSpec(**fields)


def assert_no_secret(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text, f"secret material {secret[:12]}... leaked"


# --------------------------------------------------------------------------


class TestPinning:
    def test_the_dataset_is_versioned_by_product_and_snapshot(self):
        ref = pinned_dataset("landsat7", "LANDSAT/LE07/C02/T1_L2")
        assert ref.dataset_id == "landsat7-c2-l2"
        assert ref.version == f"C02-T1-L2@{SNAPSHOT_DATE}"
        assert ref.provider == "google-earth-engine"
        assert ref.asset == "LANDSAT/LE07/C02/T1_L2"
        assert ref.source_uri and ref.source_uri.endswith("LANDSAT_LE07_C02_T1_L2")
        assert not ref.is_synthetic

    def test_the_snapshot_is_2026_11_01_in_system_version_units(self):
        assert SNAPSHOT_DATE == "2026-11-01"
        assert int(datetime(2026, 11, 1, tzinfo=UTC).timestamp()) * 1_000_000 == SNAPSHOT_MICROS

    def test_only_the_agreed_sensor_and_years_are_accepted(self):
        assert set(AGREED_SENSORS) == {"landsat7"}
        agreement = AGREED_SENSORS["landsat7"]
        assert (agreement.first_year, agreement.last_year) == (2001, 2022)
        assert agreement.agreed == "agreed with Viraj (C3), 2026-11-03"

    def test_the_service_serves_the_pinned_dataset(self):
        service = make_service()
        assert service.dataset(Indicator.NDVI) == pinned_dataset(
            "landsat7", "LANDSAT/LE07/C02/T1_L2"
        )

    def test_a_pinned_observed_request_is_accepted_by_the_contract(self):
        ref = make_service().dataset(Indicator.NDVI)
        request = AnalysisRequest(
            case_id="kariba-redd",
            project=UnitRef(unit_id="kariba-redd"),
            claim=ClaimUnderTest(name="Kariba REDD+ Project"),
            indicator=Indicator.NDVI,
            window=AnalysisWindow(pre_start=2001, pre_end=2010, post_start=2011, post_end=2022),
            datasets=(ref,),
            data_mode="observed",
        )
        assert not request.is_simulated

    def test_a_new_snapshot_changes_the_spec_hash(self, monkeypatch):
        def request_for(ref):
            return AnalysisRequest(
                case_id="kariba-redd",
                project=UnitRef(unit_id="kariba-redd"),
                claim=ClaimUnderTest(name="Kariba REDD+ Project"),
                indicator=Indicator.NDVI,
                window=AnalysisWindow(pre_start=2001, pre_end=2010, post_start=2011, post_end=2022),
                datasets=(ref,),
                data_mode="observed",
            )

        before = request_for(make_service().dataset(Indicator.NDVI)).spec_hash
        monkeypatch.setattr(catalog, "SNAPSHOT_DATE", "2027-01-01")
        after = request_for(make_service().dataset(Indicator.NDVI)).spec_hash
        assert before != after


class TestConfiguration:
    def test_the_service_implements_the_port(self):
        assert isinstance(make_service(), ObservationAccess)

    def test_no_sensor_means_no_service(self):
        with pytest.raises(ConfigurationError, match="EARTH_ENGINE_SENSOR is not set"):
            make_service(sensor=None)

    def test_a_sensor_not_agreed_under_c3_is_refused(self):
        with pytest.raises(ConfigurationError, match="not been agreed under coordination point C3"):
            make_service(sensor="landsat8")

    def test_constructing_the_service_reads_no_key_and_calls_nothing(self, tmp_path):
        backend = FakeBackend()
        make_service(backend, credentials=str(tmp_path / "missing.json"))
        assert backend.calls == []

    def test_settings_hold_the_key_as_a_secret(self):
        settings = Settings(gee_service_account_json=KEY_JSON, _env_file=None)
        assert_no_secret(repr(settings))
        assert_no_secret(str(settings.model_dump()))
        assert settings.earth_observation_configured

    def test_a_blank_key_is_no_key(self):
        settings = Settings(gee_service_account_json="  ", _env_file=None)
        assert settings.gee_service_account_json is None

    def test_settings_are_read_from_the_environment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EARTH_ENGINE_SENSOR", " Landsat7 ")
        monkeypatch.setenv("EARTH_ENGINE_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("EARTH_ENGINE_MAX_REQUESTS_PER_MINUTE", "30")
        settings = Settings(_env_file=None)
        assert settings.earth_engine_sensor == "landsat7"
        assert settings.earth_engine_cache_dir == tmp_path
        assert settings.earth_engine_max_requests_per_minute == 30

    def test_the_factory_builds_from_settings_without_contacting_anything(self, tmp_path):
        settings = Settings(earth_engine_sensor="landsat7", data_dir=tmp_path, _env_file=None)
        service = earth_engine_observations(settings)
        assert service.sensor == "landsat7"
        assert service._cache is not None
        assert service._cache.directory == tmp_path / "interim" / "earthengine"

    def test_the_factory_refuses_an_unset_sensor(self):
        with pytest.raises(ConfigurationError, match="EARTH_ENGINE_SENSOR"):
            earth_engine_observations(Settings(_env_file=None))


class TestCredentials:
    def test_a_key_file_path(self, tmp_path):
        path = tmp_path / "key.json"
        path.write_text(KEY_JSON, encoding="utf-8")
        key = load_service_account_key(SecretStr(str(path)))
        assert key.project_id == "gt-test-project"
        assert key.json_text() == KEY_JSON

    def test_the_key_contents(self):
        key = load_service_account_key(SecretStr(KEY_JSON))
        assert key.client_email == KEY_INFO["client_email"]

    @pytest.mark.parametrize(
        ("value", "match"),
        [
            (None, "GEE_SERVICE_ACCOUNT_JSON is not set"),
            ("C:/nowhere/SENTINELKEYID0123456789.json", "does not name a readable file"),
            ("{SENTINELPRIVATEKEYBODYabcdefghijklmnop0123456789", "not valid JSON"),
            (
                json.dumps({"private_key_id": "SENTINELKEYID0123456789"}),
                "not a service-account key",
            ),
        ],
    )
    def test_a_bad_key_is_a_configuration_error_that_repeats_none_of_it(self, value, match):
        with pytest.raises(ConfigurationError, match=match) as caught:
            load_service_account_key(SecretStr(value) if value is not None else None)
        assert_no_secret(str(caught.value))
        assert caught.value.__cause__ is None

    def test_the_key_never_prints(self):
        key = load_service_account_key(SecretStr(KEY_JSON))
        assert_no_secret(repr(key))
        assert_no_secret(str(key))

    def test_redaction_removes_every_secret_part(self):
        key = load_service_account_key(SecretStr(KEY_JSON))
        leaked = (
            f"bad key {KEY_JSON} / {PRIVATE_KEY} / {PRIVATE_KEY.replace(chr(10), chr(92) + 'n')}"
            f" / line {PRIVATE_KEY_BODY} / id {KEY_INFO['private_key_id']}"
            f" / {KEY_INFO['client_email']} / {KEY_INFO['client_id']}"
        )
        assert_no_secret(key.redact(leaked))


class TestSignIn:
    def test_a_missing_key_fails_before_any_call(self):
        backend = FakeBackend()
        service = make_service(backend, credentials=None)
        with pytest.raises(ConfigurationError, match="GEE_SERVICE_ACCOUNT_JSON is not set"):
            service.series(kariba_spec())
        assert backend.calls == []

    def test_a_rejected_key_is_a_configuration_error_with_nothing_chained(self):
        rejection = ee_error(f"Permission denied for {KEY_INFO['client_email']}: {PRIVATE_KEY}")
        backend = FakeBackend(failures={"initialize": [rejection]})
        service = make_service(backend)
        with pytest.raises(ConfigurationError, match="rejected the service-account") as caught:
            service.series(kariba_spec())
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__
        assert_no_secret("".join(traceback.format_exception(caught.value)))
        assert backend.count("initialize") == 1  # permanent: not retried
        assert backend.count("list_scenes") == 0

    def test_a_network_blip_at_sign_in_is_retried(self):
        backend = FakeBackend(failures={"initialize": [ConnectionError("reset")]})
        sleeps: list[float] = []
        make_service(backend, sleeps=sleeps).series(kariba_spec())
        assert backend.count("initialize") == 2
        assert sleeps[0] == 2.0

    def test_an_unreachable_sign_in_is_data_unavailable(self):
        backend = FakeBackend(failures={"initialize": [ConnectionError("down")] * 4})
        with pytest.raises(DataUnavailableError, match="could not reach Earth Engine to sign in"):
            make_service(backend).series(kariba_spec())

    def test_sign_in_happens_once(self):
        backend = FakeBackend()
        service = make_service(backend)
        service.series(kariba_spec())
        service.series(kariba_spec(start_period=2005, end_period=2010))
        assert backend.count("initialize") == 1

    def test_the_project_defaults_to_the_keys_and_can_be_overridden(self):
        backend = FakeBackend()
        make_service(backend).series(kariba_spec(end_period=2002))
        other = FakeBackend()
        make_service(other, project="my-ee-project").series(kariba_spec(end_period=2002))
        assert backend.calls[0] == ("initialize", "gt-test-project")
        assert other.calls[0] == ("initialize", "my-ee-project")

    def test_a_key_without_a_project_needs_google_cloud_project(self):
        info = {k: v for k, v in KEY_INFO.items() if k != "project_id"}
        service = make_service(credentials=json.dumps(info))
        with pytest.raises(ConfigurationError, match="GOOGLE_CLOUD_PROJECT"):
            service.series(kariba_spec())


class TestRetries:
    def test_a_transient_failure_is_retried_then_succeeds(self):
        backend = FakeBackend(
            failures={"reduce": [ConnectionError("reset"), HttpError(503, "unavailable")]}
        )
        sleeps: list[float] = []
        series = make_service(backend, sleeps=sleeps).series(kariba_spec(end_period=2002))
        assert len(series.values) == 2
        assert sleeps == [2.0, 4.0]

    def test_exhausted_retries_raise_data_unavailable(self):
        backend = FakeBackend(failures={"reduce": [HttpError(429, "too many requests")] * 10})
        sleeps: list[float] = []
        with pytest.raises(DataUnavailableError, match="after 4 attempts") as caught:
            make_service(backend, sleeps=sleeps).series(kariba_spec())
        assert backend.count("reduce") == 4
        assert sleeps == [2.0, 4.0, 8.0]
        assert caught.value.__cause__ is None

    def test_a_permanent_failure_is_not_retried(self):
        backend = FakeBackend(failures={"reduce": [ee_error("Computation timed out.")]})
        sleeps: list[float] = []
        with pytest.raises(DataUnavailableError, match="Computation timed out"):
            make_service(backend, sleeps=sleeps).series(kariba_spec())
        assert backend.count("reduce") == 1
        assert sleeps == []

    @pytest.mark.parametrize(
        ("error", "kind"),
        [
            (ConnectionError("reset by peer"), TransientError),
            (TimeoutError("read timed out"), TransientError),
            (HttpError(429), TransientError),
            (HttpError(503), TransientError),
            (ee_error("Too many concurrent aggregations."), TransientError),
            (ee_error("Earth Engine capacity exceeded."), TransientError),
            (ee_error("Computation timed out."), PermanentError),
            (ee_error("User memory limit exceeded."), PermanentError),
            (ee_error("Image.load: Image asset 'X' not found."), PermanentError),
            (ee_error("Permission denied."), PermanentError),
            (HttpError(404), PermanentError),
            (HttpError(400), PermanentError),
            (ValueError("something nobody anticipated"), PermanentError),
        ],
    )
    def test_classification(self, error, kind):
        assert isinstance(classify(error), kind)

    def test_classification_redacts_the_key(self):
        key = load_service_account_key(SecretStr(KEY_JSON))
        assert_no_secret(str(classify(ee_error(f"oops {PRIVATE_KEY}"), key)))

    def test_the_last_delay_repeats(self):
        policy = RetryPolicy(max_attempts=6, delays_s=(1.0, 3.0))
        assert [policy.delay(n) for n in range(1, 6)] == [1.0, 3.0, 3.0, 3.0, 3.0]

    def test_call_with_retry_passes_a_permanent_error_through_at_once(self):
        calls = []

        def fail():
            calls.append(1)
            raise PermanentError("no")

        with pytest.raises(PermanentError):
            call_with_retry(fail, policy=RetryPolicy(), sleep=lambda s: None)
        assert len(calls) == 1


class TestRateLimiting:
    def test_calls_are_spaced_evenly(self):
        waits: list[float] = []
        limiter = RateLimiter(60, clock=lambda: 100.0, sleep=waits.append)
        assert [limiter.acquire() for _ in range(3)] == [0.0, 1.0, 2.0]
        assert waits == [1.0, 2.0]

    def test_no_wait_once_the_interval_has_passed(self):
        now = [0.0]
        limiter = RateLimiter(120, clock=lambda: now[0], sleep=lambda s: None)
        limiter.acquire()
        now[0] = 5.0
        assert limiter.acquire() == 0.0

    def test_every_earth_engine_call_goes_through_the_limiter(self):
        acquired = []

        class Counting(RateLimiter):
            def acquire(self) -> float:
                acquired.append(1)
                return 0.0

        backend = FakeBackend()
        make_service(backend, rate_limiter=Counting(60)).series(kariba_spec(end_period=2003))
        assert len(acquired) == len(backend.calls)


class TestSeries:
    def test_one_value_and_one_observation_count_per_year(self):
        series = make_service().series(kariba_spec())
        assert series.periods == tuple(range(2001, 2023))
        assert series.indicator is Indicator.NDVI
        assert series.unit == "ndvi"
        assert series.n_valid_observations is not None
        assert len(series.n_valid_observations) == 22
        assert series.values[0] == pytest.approx(0.401)
        # 10 zeros, 10 threes, 10 fours, 15 fives...: the 30th and 31st of 60 are 4 and 5.
        assert set(series.n_valid_observations) == {4}

    def test_the_engines_spec_reaches_earth_engine_unchanged(self):
        backend = FakeBackend()
        make_service(backend).series(kariba_spec(end_period=2002))
        query = next(q for name, q in backend.calls if name == "reduce")
        expected = next(
            s
            for s in describe_engine()["reduction"]["specs"]
            if s["sensor"] == "landsat7" and s["indicator"] == "ndvi"
        )
        assert query.reduction == expected
        assert query.collection == "LANDSAT/LE07/C02/T1_L2"
        assert query.scale_m == 30
        assert query.snapshot_micros == SNAPSHOT_MICROS
        assert query.geometry == SQUARE

    def test_a_year_with_no_clear_pixel_is_reported_not_filled(self):
        backend = FakeBackend(
            years={2005: {**default_year(2005), "mean": None, "histogram": {"0": 60}}}
        )
        series = make_service(backend).series(kariba_spec())
        i = series.periods.index(2005)
        assert math.isnan(series.values[i])
        assert series.n_valid_observations[i] == 0

    def test_a_year_with_no_scenes_at_all_is_nan_with_zero_observations(self):
        backend = FakeBackend(
            years={
                2003: {"ids": [], "versions": [], "n_available": 0, "mean": None, "histogram": {}}
            }
        )
        series = make_service(backend).series(kariba_spec())
        i = series.periods.index(2003)
        assert math.isnan(series.values[i])
        assert series.n_valid_observations[i] == 0
        reduced_years = [q.year for name, q in backend.calls if name == "reduce"]
        assert 2003 not in reduced_years

    def test_a_year_emptied_by_the_snapshot_filter_says_so(self):
        backend = FakeBackend(
            years={
                2014: {"ids": [], "versions": [], "n_available": 23, "mean": None, "histogram": {}}
            }
        )
        with pytest.raises(DataUnavailableError) as caught:
            make_service(backend).series(kariba_spec())
        message = str(caught.value)
        assert "2014: all 23" in message
        assert "removed by the snapshot filter" in message
        assert SNAPSHOT_DATE in message

    def test_an_inconsistent_reduction_is_refused(self):
        backend = FakeBackend(years={2002: {**default_year(2002), "histogram": {"0": 60}}})
        with pytest.raises(DataUnavailableError, match="inconsistent reduction"):
            make_service(backend).series(kariba_spec())

    def test_a_geometry_with_no_pixel_is_refused(self):
        backend = FakeBackend(years={2002: {**default_year(2002), "histogram": {}}})
        with pytest.raises(DataUnavailableError, match="covers no pixel"):
            make_service(backend).series(kariba_spec())

    def test_a_listing_that_cannot_be_fingerprinted_is_refused(self):
        backend = FakeBackend(years={2002: {**default_year(2002), "versions": [1]}})
        with pytest.raises(DataUnavailableError, match="cannot be fingerprinted"):
            make_service(backend).series(kariba_spec())

    @pytest.mark.parametrize(
        ("spec", "match"),
        [
            (kariba_spec(geometry=None), "has no geometry"),
            (kariba_spec(buffer_m=300.0), "inward buffer"),
            (kariba_spec(composite="annual-mean"), "composite"),
            (kariba_spec(start_period=2000), r"years \[2000\]"),
            (kariba_spec(end_period=2023), r"years \[2023\]"),
            (kariba_spec(indicator=Indicator.FOREST_AREA_HA), "spectral indices only"),
            (kariba_spec(start_period=2005, end_period=2005), "at least two years"),
        ],
    )
    def test_requests_outside_the_agreement_are_refused_before_any_call(self, spec, match):
        backend = FakeBackend()
        # No credentials: a refusal here must not depend on signing in first.
        service = make_service(backend, credentials=None)
        with pytest.raises(DataUnavailableError, match=match):
            service.series(spec)
        assert backend.calls == []

    def test_histogram_median_matches_numpy(self):
        rng = np.random.default_rng(22)
        for _ in range(200):
            values = rng.integers(0, 12, size=int(rng.integers(1, 40)))
            counts: dict[int, int] = {}
            for v in values:
                counts[int(v)] = counts.get(int(v), 0) + 1
            assert histogram_median(counts) == int(np.median(values))

    def test_the_scene_fingerprint_ignores_order_but_not_versions(self):
        a = scene_fingerprint(["x", "y"], [1, 2])
        assert a == scene_fingerprint(["y", "x"], [2, 1])
        assert a != scene_fingerprint(["x", "y"], [1, 3])


class TestProvenance:
    def test_provenance_records_the_pin_the_c3_decisions_and_every_year(self):
        service = make_service()
        spec = kariba_spec()
        service.series(spec)
        provenance = service.provenance(spec)
        p = provenance.parameters
        assert provenance.stage == "ingestion"
        assert provenance.source_uri and "LANDSAT_LE07_C02_T1_L2" in provenance.source_uri
        assert p["dataset"] == f"landsat7-c2-l2@C02-T1-L2@{SNAPSHOT_DATE}"
        assert p["snapshot_date"] == SNAPSHOT_DATE
        assert p["sensor_selection"] == (
            "landsat7 for 2001-2022, agreed with Viraj (C3), 2026-11-03"
        )
        assert "max_cloud_fraction is not applied" in p["cloud_filter"]
        assert "Agreed with Viraj (C3), 2026-11-03" in p["cloud_filter"]
        assert p["requested_max_cloud_fraction"] == 0.4
        assert p["reduction"]["bands"] == {"nir": "SR_B4", "red": "SR_B3"}
        assert len(p["years"]) == 22
        assert all(y["scene_fingerprint"] for y in p["years"].values())
        assert p["geometry_blake2b"]

    def test_provenance_before_any_series_still_names_the_pin(self):
        provenance = make_service().provenance(kariba_spec())
        assert provenance.parameters["snapshot_date"] == SNAPSHOT_DATE
        assert "years" not in provenance.parameters


class TestCache:
    def test_hits_and_misses_are_counted_for_the_cache_hit_rate(self, tmp_path):
        """gt_cache_requests_total{cache="reduction"} (#50): one lookup per year."""
        from groundtruth.platform.metrics import REGISTRY

        def count(result: str) -> float:
            labels = {"cache": "reduction", "result": result}
            return REGISTRY.get_sample_value("gt_cache_requests_total", labels) or 0.0

        hits, misses = count("hit"), count("miss")
        make_service(FakeBackend(), cache_dir=tmp_path).series(kariba_spec())
        assert (count("hit") - hits, count("miss") - misses) == (0, 22)
        make_service(FakeBackend(), credentials=None, cache_dir=tmp_path).series(kariba_spec())
        assert (count("hit") - hits, count("miss") - misses) == (22, 22)

    def test_a_second_run_is_served_from_the_cache_without_signing_in(self, tmp_path):
        first = make_service(FakeBackend(), cache_dir=tmp_path).series(kariba_spec())

        backend = FakeBackend()
        service = make_service(backend, credentials=None, cache_dir=tmp_path)
        second = service.series(kariba_spec())

        assert backend.calls == []
        assert second.n_valid_observations == first.n_valid_observations
        assert second.values == pytest.approx(first.values, nan_ok=True)
        years = service.provenance(kariba_spec()).parameters["years"]
        assert all(y["cache_hit"] for y in years.values())

    def test_nan_survives_the_cache(self, tmp_path):
        backend = FakeBackend(
            years={2005: {**default_year(2005), "mean": None, "histogram": {"0": 60}}}
        )
        make_service(backend, cache_dir=tmp_path).series(kariba_spec())
        cached = make_service(credentials=None, cache_dir=tmp_path).series(kariba_spec())
        assert math.isnan(cached.values[cached.periods.index(2005)])

    def test_the_entry_holds_the_full_key(self, tmp_path):
        make_service(cache_dir=tmp_path).series(kariba_spec(end_period=2002))
        entries = [json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("*.json")]
        assert sorted(e["key"]["year"] for e in entries) == [2001, 2002]
        stored = next(e for e in entries if e["key"]["year"] == 2001)
        key = stored["key"]
        assert key["dataset"]["version"] == f"C02-T1-L2@{SNAPSHOT_DATE}"
        assert key["dataset"]["asset"] == "LANDSAT/LE07/C02/T1_L2"
        assert key["reduction"]["mask"]["invalid_bits"] == [0, 1, 2, 3, 4, 5]
        assert key["geometry_blake2b"]
        assert stored["value"]["scene_fingerprint"]
        assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]

    def test_a_different_geometry_misses(self, tmp_path):
        make_service(cache_dir=tmp_path).series(kariba_spec())
        moved = {**SQUARE, "coordinates": [[[x + 1, y] for x, y in SQUARE["coordinates"][0]]]}
        backend = FakeBackend()
        make_service(backend, cache_dir=tmp_path).series(kariba_spec(geometry=moved))
        assert backend.count("reduce") == 22

    def test_a_methodology_change_misses(self, tmp_path):
        make_service(cache_dir=tmp_path).series(kariba_spec())
        reduction = json.loads(json.dumps(describe_engine()["reduction"]))
        for spec in reduction["specs"]:
            spec["mask"].setdefault("invalid_bits", []).append(7)
        backend = FakeBackend()
        make_service(backend, cache_dir=tmp_path, reduction=reduction).series(kariba_spec())
        assert backend.count("reduce") == 22

    def test_a_new_snapshot_misses(self, tmp_path, monkeypatch):
        make_service(cache_dir=tmp_path).series(kariba_spec())
        monkeypatch.setattr(catalog, "SNAPSHOT_DATE", "2027-01-01")
        backend = FakeBackend()
        make_service(backend, cache_dir=tmp_path).series(kariba_spec())
        assert backend.count("reduce") == 22

    @pytest.mark.parametrize("damage", ["tampered_key", "corrupt"])
    def test_a_damaged_entry_is_a_miss_and_is_rewritten(self, tmp_path, damage):
        make_service(cache_dir=tmp_path).series(kariba_spec(end_period=2002))
        entry = next(
            p
            for p in tmp_path.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8"))["key"]["year"] == 2001
        )
        if damage == "corrupt":
            entry.write_text("{not json", encoding="utf-8")
        else:
            stored = json.loads(entry.read_text(encoding="utf-8"))
            stored["key"]["year"] = 1999
            entry.write_text(json.dumps(stored), encoding="utf-8")

        backend = FakeBackend()
        make_service(backend, cache_dir=tmp_path).series(kariba_spec(end_period=2002))
        assert [q.year for name, q in backend.calls if name == "reduce"] == [2001]
        assert json.loads(entry.read_text(encoding="utf-8"))["key"]["year"] == 2001

    def test_a_failure_is_never_cached(self, tmp_path):
        backend = FakeBackend(failures={"reduce": [ee_error("Computation timed out.")]})
        with pytest.raises(DataUnavailableError):
            make_service(backend, cache_dir=tmp_path).series(kariba_spec(end_period=2002))
        assert not list(tmp_path.glob("*.json"))


class TestCredentialsNeverLogged:
    def test_no_log_record_message_or_traceback_carries_the_key(self, caplog):
        caplog.set_level(logging.DEBUG)
        leaky = f"{KEY_INFO['client_email']} {PRIVATE_KEY} {KEY_INFO['private_key_id']}"
        backend = FakeBackend(
            failures={
                "initialize": [ConnectionError(f"reset while sending {leaky}")],
                "list_scenes": [HttpError(503, f"unavailable {leaky}")],
                "reduce": [ee_error(f"User memory limit exceeded {leaky}")],
            }
        )
        with pytest.raises(DataUnavailableError) as caught:
            make_service(backend).series(kariba_spec())

        assert caplog.records, "the retries should have been logged"
        for record in caplog.records:
            assert_no_secret(record.getMessage())
            assert_no_secret(repr(record.__dict__))
        assert_no_secret(caplog.text)
        assert_no_secret("".join(traceback.format_exception(caught.value)))


class TestNoFixtureFallback:
    OBSERVED_PATH = ("observation.py", "earthengine.py", "catalog.py", "cache.py", "resilience.py")

    def test_the_observed_path_never_imports_the_synthetic_provider(self):
        for name in self.OBSERVED_PATH:
            tree = ast.parse((SRC / "platform/datasets" / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module, *(a.name for a in node.names)]
                elif isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                for module in modules:
                    assert "synthetic" not in module.lower(), f"{name} imports {module}"
                    assert "fixture" not in module.lower(), f"{name} imports {module}"

    def test_every_failure_raises_rather_than_returning_a_series(self):
        backend = FakeBackend(failures={"list_scenes": [ee_error("Asset not found.")]})
        with pytest.raises(DataUnavailableError):
            make_service(backend).series(kariba_spec())

    def test_observed_runs_still_refuse_until_every_port_is_real(self):
        request = AnalysisRequest(
            case_id="kariba-redd",
            project=UnitRef(unit_id="kariba-redd"),
            claim=ClaimUnderTest(name="Kariba REDD+ Project"),
            indicator=Indicator.NDVI,
            window=AnalysisWindow(pre_start=2001, pre_end=2010, post_start=2011, post_end=2022),
            data_mode="observed",
        )
        with pytest.raises(DataUnavailableError, match="not implemented") as caught:
            earth_engine_access(request)
        assert "silent fallback to synthetic fixtures is strictly prohibited" in str(caught.value)
