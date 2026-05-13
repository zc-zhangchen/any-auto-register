"""Table-driven tests for canonical_hash and mask_credential."""

from __future__ import annotations

import hashlib
import re

import pytest

from core.pools.canonical import canonical_hash, mask_credential


HEX64 = re.compile(r"^[a-f0-9]{64}$")


@pytest.mark.parametrize(
    "provider, auth_type, credential, refresh_token",
    [
        ("gpt", "apikey", "sk-fake-quickstart", None),
        ("grok", "cookie", "eyJfake.sso.grok.01", None),
        ("cursor", "cookie", "WorkosCursorSessionToken=fake.x", None),
        ("gpt", "oauth", "", "eyJfake.refresh"),
        ("kiro", "oauth", "", "M.C514_fake.refresh"),
        ("openblocklabs", "apikey", "obl_fake_06", None),
        ("tavily", "apikey", "tvly-fake-07", None),
        ("gpt", "oauth", "", None),  # both empty — well-defined fallback
    ],
)
def test_returns_64_lowercase_hex(provider, auth_type, credential, refresh_token):
    h = canonical_hash(provider, auth_type, credential, refresh_token)
    assert HEX64.match(h), h


def test_payload_uses_lowercased_provider_and_auth_type():
    a = canonical_hash("GPT", "OAUTH", "", "tok")
    b = canonical_hash("gpt", "oauth", "", "tok")
    assert a == b


def test_credential_is_trimmed():
    a = canonical_hash("gpt", "apikey", "  sk-fake-x  ", None)
    b = canonical_hash("gpt", "apikey", "sk-fake-x", None)
    assert a == b


def test_refresh_token_fallback_when_credential_empty():
    a = canonical_hash("gpt", "oauth", "", "eyJfake.refresh")
    b = canonical_hash("gpt", "oauth", None, "eyJfake.refresh")  # type: ignore[arg-type]
    assert a == b


def test_credential_wins_over_refresh_token_when_both_present():
    a = canonical_hash("gpt", "oauth", "primary", "ignored")
    b = canonical_hash("gpt", "oauth", "primary", None)
    assert a == b


def test_whitespace_only_credential_falls_back_to_refresh():
    a = canonical_hash("gpt", "oauth", "   ", "fallback")
    b = canonical_hash("gpt", "oauth", "", "fallback")
    assert a == b


def test_byte_exact_against_manual_sha256():
    expected = hashlib.sha256(b"gpt\noauth\neyJfake.refresh").hexdigest()
    assert canonical_hash("gpt", "oauth", "", "eyJfake.refresh") == expected


def test_none_provider_raises():
    with pytest.raises(ValueError):
        canonical_hash(None, "apikey", "x", None)  # type: ignore[arg-type]


def test_none_auth_type_raises():
    with pytest.raises(ValueError):
        canonical_hash("gpt", None, "x", None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", "…"),
        ("ab", "…"),
        ("abc", "…"),
        ("abcd", "a…d"),
        ("abcdefghij", "a…j"),
        ("abcdefghijkl", "abcd…ijkl"),
        ("sk-fake-longer-credential", "sk-f…tial"),
    ],
)
def test_mask_credential_buckets(raw, expected):
    assert mask_credential(raw) == expected
