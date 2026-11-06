from __future__ import annotations

import pytest

from groundtruth.platform.auth import passwords
from groundtruth.platform.auth.ratelimit import FailureLimiter


def test_default_cost_round_trip_and_format():
    stored = passwords.hash_password("a long enough pass")
    algo, n, r, p, _salt, _digest = stored.split("$")
    assert (algo, int(n), int(r), int(p)) == ("scrypt", 2**15, 8, 1)
    assert passwords.verify_password("a long enough pass", stored)
    assert not passwords.verify_password("another long pass", stored)
    assert not passwords.needs_rehash(stored)
    assert "a long enough pass" not in stored


def test_salts_differ():
    assert passwords.hash_password("same password 1") != passwords.hash_password("same password 1")


def test_stale_parameters_need_rehash(monkeypatch):
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    stored = passwords.hash_password("a long enough pass")
    monkeypatch.undo()
    assert passwords.needs_rehash(stored)
    assert passwords.verify_password("a long enough pass", stored)


@pytest.mark.parametrize("bad", ["", "scrypt$1$2", "md5$1$1$1$AA==$AA==", "scrypt$x$8$1$AA==$AA=="])
def test_malformed_hash_never_matches(bad):
    assert not passwords.verify_password("anything at all", bad)
    assert passwords.needs_rehash(bad)


def test_absurd_cost_is_refused():
    stored = "scrypt$1073741824$8$1$AAAA$AAAA"
    assert not passwords.verify_password("x" * 12, stored)


@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("short", False),
        ("x" * 129, False),
        ("password123", False),
        ("aaaaaaaaaaaa", False),
        ("me@example.org", False),
        ("a perfectly fine one", True),
    ],
)
def test_policy(password, ok):
    assert (passwords.check_policy(password, "me@example.org") is None) is ok


def test_limiter_window():
    now = [0.0]
    limiter = FailureLimiter(max_failures=2, window=100, clock=lambda: now[0])
    key = ("a@b.c", "1.1.1.1")
    assert limiter.retry_after(key) is None
    limiter.record_failure(key)
    limiter.record_failure(key)
    assert limiter.retry_after(key) is not None
    assert limiter.retry_after(("a@b.c", "2.2.2.2")) is None
    now[0] = 101
    assert limiter.retry_after(key) is None
