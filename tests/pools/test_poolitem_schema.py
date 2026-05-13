"""Validation tests for PoolItem schema (T015 → spec.md FR-001..FR-006)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.pools.canonical import canonical_hash
from core.pools.schema import PoolItem, PoolItemSource


def _src() -> PoolItemSource:
    return PoolItemSource(
        task_id="t-test",
        registered_at="2026-05-13T03:14:15Z",
        executor="protocol",
    )


def _build(**overrides):
    """Construct a valid PoolItem with optional overrides for negative tests."""
    provider = overrides.pop("provider", "gpt")
    auth_type = overrides.pop("auth_type", "apikey")
    credential = overrides.pop("credential", "sk-fake-x")
    refresh_token = overrides.pop("refresh_token", None)
    credential_hash = overrides.pop(
        "credential_hash",
        canonical_hash(provider, auth_type, credential, refresh_token),
    )
    return PoolItem(
        provider=provider,
        auth_type=auth_type,
        credential=credential,
        credential_hash=credential_hash,
        refresh_token=refresh_token,
        source=overrides.pop("source", _src()),
        **overrides,
    )


def test_valid_minimal_apikey():
    item = _build()
    assert item.provider == "gpt"
    assert item.schema_version == "1.0"


def test_missing_required_provider():
    with pytest.raises(ValidationError) as exc:
        PoolItem(
            auth_type="apikey",
            credential="x",
            credential_hash=canonical_hash("gpt", "apikey", "x"),
            source=_src(),
        )
    assert "provider" in str(exc.value)


def test_missing_required_auth_type():
    with pytest.raises(ValidationError):
        PoolItem(
            provider="gpt",
            credential="x",
            credential_hash=canonical_hash("gpt", "apikey", "x"),
            source=_src(),
        )


def test_missing_required_source():
    with pytest.raises(ValidationError):
        PoolItem(
            provider="gpt",
            auth_type="apikey",
            credential="x",
            credential_hash=canonical_hash("gpt", "apikey", "x"),
        )


def test_cookie_requires_non_empty_credential():
    with pytest.raises(ValidationError) as exc:
        _build(auth_type="cookie", credential="")
    assert "cookie" in str(exc.value)


def test_apikey_requires_non_empty_credential():
    with pytest.raises(ValidationError) as exc:
        _build(auth_type="apikey", credential="")
    assert "apikey" in str(exc.value)


def test_oauth_all_three_tokens_empty_is_rejected():
    with pytest.raises(ValidationError) as exc:
        _build(
            auth_type="oauth",
            credential="",
            refresh_token=None,
            access_token=None,
            credential_hash=canonical_hash("gpt", "oauth", "", None),
        )
    assert "oauth" in str(exc.value)


def test_oauth_accepts_refresh_token_only():
    item = _build(
        auth_type="oauth",
        credential="",
        refresh_token="eyJfake.refresh",
    )
    assert item.refresh_token == "eyJfake.refresh"


def test_oauth_accepts_access_token_only():
    # canonical_hash falls back to "" since access_token is not in the algorithm
    h = canonical_hash("gpt", "oauth", "", None)
    item = PoolItem(
        provider="gpt",
        auth_type="oauth",
        credential="",
        access_token="eyJfake.access",
        credential_hash=h,
        source=_src(),
    )
    assert item.access_token == "eyJfake.access"


def test_credential_hash_mismatch_is_rejected():
    with pytest.raises(ValidationError) as exc:
        _build(credential_hash="0" * 64)
    assert "credential_hash" in str(exc.value)


def test_credential_hash_must_be_lower_hex():
    with pytest.raises(ValidationError):
        _build(credential_hash="A" * 64)  # uppercase
    with pytest.raises(ValidationError):
        _build(credential_hash="zz" + "0" * 62)  # non-hex


def test_credential_hash_length():
    with pytest.raises(ValidationError):
        _build(credential_hash="abc")


def test_meta_depth_exceeded_is_rejected():
    # depth 5: a -> b -> c -> d -> "leaf"
    deep = {"a": {"b": {"c": {"d": {"e": "leaf"}}}}}
    with pytest.raises(ValidationError) as exc:
        _build(meta=deep)
    assert "meta" in str(exc.value)


def test_meta_depth_at_max_is_accepted():
    # depth 4
    ok = {"a": {"b": {"c": {"d": "leaf"}}}}
    item = _build(meta=ok)
    assert item.meta == ok


def test_extra_fields_are_preserved_forward_compat():
    h = canonical_hash("gpt", "apikey", "sk-fake-fc", None)
    item = PoolItem(
        provider="gpt",
        auth_type="apikey",
        credential="sk-fake-fc",
        credential_hash=h,
        source=_src(),
        mfa_seed="FAKE",  # type: ignore[call-arg]
    )
    dumped = item.model_dump(exclude_none=False)
    assert dumped.get("mfa_seed") == "FAKE"


def test_schema_version_2x_rejected():
    h = canonical_hash("gpt", "apikey", "x", None)
    with pytest.raises(ValidationError) as exc:
        PoolItem(
            schema_version="2.0",
            provider="gpt",
            auth_type="apikey",
            credential="x",
            credential_hash=h,
            source=_src(),
        )
    assert "schema_version" in str(exc.value)


def test_weight_out_of_range():
    with pytest.raises(ValidationError):
        _build(weight=0)
    with pytest.raises(ValidationError):
        _build(weight=10001)


def test_weight_at_boundaries():
    assert _build(weight=1).weight == 1
    assert _build(weight=10000).weight == 10000


def test_invalid_executor_in_source():
    with pytest.raises(ValidationError):
        PoolItemSource(
            task_id="t", registered_at="2026-05-13T03:14:15Z", executor="manual"  # type: ignore[arg-type]
        )


def test_source_extra_rejected():
    with pytest.raises(ValidationError):
        PoolItemSource(
            task_id="t",
            registered_at="2026-05-13T03:14:15Z",
            executor="protocol",
            unexpected="x",  # type: ignore[call-arg]
        )
