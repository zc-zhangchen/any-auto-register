"""Tests for the reference Grok adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.pools.adapters.grok_adapter import to_pool_item
from core.pools.canonical import canonical_hash


def _account(**kw):
    """Build a duck-typed Grok account object."""
    base = dict(sso="eyJfake.sso.grok.unit", email="unit@fake.example", expires_at=None, proxy_hint=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_adapter_produces_valid_pool_item():
    item = to_pool_item(
        _account(),
        task_id="t-grok-1",
        registered_at="2026-05-13T03:14:15Z",
        executor="headed",
        registrar_version="0.9.0",
    )
    assert item.provider == "grok"
    assert item.auth_type == "cookie"
    assert item.credential == "eyJfake.sso.grok.unit"
    assert item.email == "unit@fake.example"


def test_adapter_credential_hash_is_auto_computed():
    item = to_pool_item(
        _account(sso="eyJfake.sso.grok.42"),
        task_id="t-grok-2",
        registered_at="2026-05-13T03:14:15Z",
        executor="protocol",
    )
    expected = canonical_hash("grok", "cookie", "eyJfake.sso.grok.42")
    assert item.credential_hash == expected


def test_adapter_passes_through_proxy_and_weight():
    acct = _account(sso="eyJfake.sso.grok.43", proxy_hint="http://198.51.100.43:8080")
    item = to_pool_item(
        acct,
        task_id="t-grok-3",
        registered_at="2026-05-13T03:14:15Z",
        executor="protocol",
        weight=200,
        meta={"client_id": "grok-client-x"},
    )
    assert item.proxy_hint == "http://198.51.100.43:8080"
    assert item.weight == 200
    assert item.meta == {"client_id": "grok-client-x"}


def test_adapter_rejects_empty_sso():
    with pytest.raises(ValueError, match="sso"):
        to_pool_item(
            _account(sso=""),
            task_id="t-grok-4",
            registered_at="2026-05-13T03:14:15Z",
            executor="protocol",
        )


def test_adapter_rejects_missing_sso_attribute():
    bare = SimpleNamespace()
    with pytest.raises(ValueError):
        to_pool_item(
            bare,
            task_id="t-grok-5",
            registered_at="2026-05-13T03:14:15Z",
            executor="protocol",
        )


def test_adapter_source_fields_propagate():
    item = to_pool_item(
        _account(),
        task_id="t-grok-6",
        registered_at="2026-05-13T03:14:15Z",
        executor="headless",
        registrar_version="1.2.3",
    )
    assert item.source.task_id == "t-grok-6"
    assert item.source.executor == "headless"
    assert item.source.registrar_version == "1.2.3"
