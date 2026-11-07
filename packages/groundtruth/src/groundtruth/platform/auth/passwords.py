"""Password hashing and policy. Nothing here logs, and nothing returns a password.

Stored format: ``scrypt$n$r$p$salt_b64$hash_b64``. The cost parameters travel with each
hash so they can be raised later; :func:`needs_rehash` says when a stored hash is stale.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32
MIN_LENGTH = 10
MAX_LENGTH = 128

COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "passw0rd123",
        "1234567890",
        "12345678910",
        "123456789012",
        "qwertyuiop",
        "qwerty1234",
        "qwerty12345",
        "1q2w3e4r5t",
        "iloveyou12",
        "letmein123",
        "welcome123",
        "admin12345",
        "administrator",
        "changeme123",
        "abcdefghij",
        "abc1234567",
        "groundtruth",
        "groundtruth1",
        "groundtruth123",
        "0123456789",
        "1111111111",
        "0000000000",
    }
)


def _maxmem(n: int, r: int) -> int:
    # scrypt needs about 128*n*r bytes; OpenSSL's default cap is exactly 32 MiB.
    return 128 * n * r * 2 + (1 << 20)


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=KEY_BYTES,
        maxmem=_maxmem(n, r),
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    b64 = base64.b64encode
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}"
        f"${b64(salt).decode('ascii')}${b64(digest).decode('ascii')}"
    )


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4], validate=True)
        digest = base64.b64decode(parts[5], validate=True)
    except (ValueError, binascii.Error):
        return None
    # Refuse parameters that would make verification a denial-of-service lever.
    if not (2**10 <= n <= 2**20 and n & (n - 1) == 0 and 1 <= r <= 32 and 1 <= p <= 16):
        return None
    return n, r, p, salt, digest


def verify_password(password: str, stored: str) -> bool:
    """True when ``password`` matches ``stored``. A malformed hash never matches."""
    parsed = _parse(stored)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=_maxmem(n, r),
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    parsed = _parse(stored)
    if parsed is None:
        return True
    n, r, p, _salt, digest = parsed
    return (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P) or len(digest) != KEY_BYTES


_dummy_hash: str | None = None


def dummy_verify(password: str) -> None:
    """Spend the same time as a real verification, for an email that has no account."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _dummy_hash)


def check_policy(password: str, email: str) -> str | None:
    """A human-readable reason the password is unacceptable, or ``None`` when it is fine."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    lowered = password.lower()
    if lowered == email.strip().lower():
        return "The password must not be your email address."
    if lowered in COMMON_PASSWORDS or len(set(lowered)) == 1:
        return "That password is too common. Choose something less guessable."
    return None
