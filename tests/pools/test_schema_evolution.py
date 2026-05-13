"""Schema-evolution / forward-compat tests (T024, Phase 5 US3 — upstream side).

Validates that a v1.0 parser keeps reading v1.1+ payloads (FR-012), that
``schema_version`` defaults preserve register-to-pool style callers
(FR-011), and that explicit ``null`` keeps distinct semantics from key
absence (FR-002).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from core.pools.canonical import canonical_hash
from core.pools.schema import PoolItem, PoolItemSource


def _by_case(samples):
    return {d["_case"]: d for d in samples}


def _payload(d):
    return {k: v for k, v in d.items() if k != "_case"}


def _src():
    return PoolItemSource(
        task_id="t-evo", registered_at="2026-05-13T03:14:15Z", executor="protocol"
    )


# ---------- (a) v1.0 parser ingests v1.1 payload ----------


def test_v1_0_parser_accepts_v1_1_with_unknown_field(golden_samples):
    """FR-012 + FR-011: case 14 carries schema_version=1.1 + unknown ``mfa_seed``."""
    payload = _payload(_by_case(golden_samples)["14_future_schema_1_1_with_unknown_field"])
    item = PoolItem.model_validate(payload)

    assert item.schema_version == "1.1"
    # Unknown field survives via extra='allow'
    assert item.__pydantic_extra__ is not None
    assert item.__pydantic_extra__.get("mfa_seed") == "FAKE_MFA_SEED_DO_NOT_USE"


def test_dump_round_trips_v1_1_unknown_field(golden_samples):
    """A v1.0 parser must NOT drop a v1.1 unknown field on dump."""
    payload = _payload(_by_case(golden_samples)["14_future_schema_1_1_with_unknown_field"])
    item = PoolItem.model_validate(payload)

    dumped = item.model_dump(exclude_none=False)
    assert dumped["mfa_seed"] == "FAKE_MFA_SEED_DO_NOT_USE"


# ---------- (b) "v1.1 reader" tolerates absent new field on v1.0 payload ----------


def test_v1_0_payload_missing_future_field_uses_default(golden_samples):
    """FR-012: a v1.0 payload missing a future optional field defaults to None.

    We model "the future v1.1 parser" as: still a PoolItem (the live schema),
    but the caller looks for a new optional field. Absence MUST mean None,
    not raise.
    """
    payload = _payload(_by_case(golden_samples)["09_minimal_required_only"])
    item = PoolItem.model_validate(payload)

    # All declared optional fields default to None when absent
    assert item.weight is None
    assert item.email is None
    assert item.expires_at is None
    assert item.region is None
    assert item.meta is None
    assert item.refresh_token is None

    # Hypothetical "v1.1 new field" addressed via __pydantic_extra__:
    extra = item.__pydantic_extra__ or {}
    assert "mfa_seed" not in extra  # absent, not null


# ---------- (c) Explicit null vs key-absence (FR-002 守则 3) ----------


def test_explicit_null_in_meta_is_distinct_from_missing(golden_samples):
    """FR-002 守则 3: meta key with value=null is NOT the same as key absent.

    Fixture case 08 carries ``meta.region_hint: null`` explicitly.
    """
    payload = _payload(_by_case(golden_samples)["08_meta_explicit_null"])
    item = PoolItem.model_validate(payload)

    assert item.meta is not None
    assert "region_hint" in item.meta  # key is present
    assert item.meta["region_hint"] is None  # value is null
    assert item.meta["trial_quota"] == 5000  # sibling unaffected


def test_explicit_null_survives_round_trip():
    """Round-trip via JSON: explicit null stays an explicit null in meta."""
    payload = {
        "provider": "openblocklabs",
        "auth_type": "apikey",
        "credential": "obl-fake-roundtrip",
        "credential_hash": canonical_hash("openblocklabs", "apikey", "obl-fake-roundtrip"),
        "meta": {"slot_a": None, "slot_b": "set"},
        "source": _src().model_dump(),
    }
    item = PoolItem.model_validate(payload)
    blob = item.model_dump_json()
    reparsed = PoolItem.model_validate(json.loads(blob))

    assert reparsed.meta is not None
    assert "slot_a" in reparsed.meta
    assert reparsed.meta["slot_a"] is None
    assert reparsed.meta["slot_b"] == "set"


def test_key_absence_in_meta_is_distinct_from_null():
    """The two payloads below MUST decode into different meta dicts."""
    base = dict(
        provider="openblocklabs",
        auth_type="apikey",
        credential="obl-fake-absence",
        credential_hash=canonical_hash("openblocklabs", "apikey", "obl-fake-absence"),
        source=_src().model_dump(),
    )
    with_null = PoolItem.model_validate({**base, "meta": {"slot_x": None}})
    without_key = PoolItem.model_validate({**base, "meta": {}})

    assert with_null.meta == {"slot_x": None}
    assert without_key.meta == {}
    assert "slot_x" in (with_null.meta or {})
    assert "slot_x" not in (without_key.meta or {})


# ---------- (d) Boundary: 2.x is rejected, 1.x default works ----------


def test_schema_version_default_is_1_0_when_absent():
    """FR-011: missing schema_version falls back to '1.0'."""
    item = PoolItem.model_validate({
        "provider": "gpt",
        "auth_type": "apikey",
        "credential": "sk-fake-default-version",
        "credential_hash": canonical_hash("gpt", "apikey", "sk-fake-default-version"),
        "source": _src().model_dump(),
    })
    assert item.schema_version == "1.0"


def test_schema_version_2_x_rejected_with_invalid_schema_version_intent():
    """FR-011: a v1.x parser MUST refuse 2.x payloads (invalid_schema_version)."""
    with pytest.raises(ValidationError) as exc:
        PoolItem.model_validate({
            "schema_version": "2.0",
            "provider": "gpt",
            "auth_type": "apikey",
            "credential": "sk-fake-future",
            "credential_hash": canonical_hash("gpt", "apikey", "sk-fake-future"),
            "source": _src().model_dump(),
        })
    assert "schema_version" in str(exc.value)


def test_minor_bump_within_1_x_is_accepted(golden_samples):
    """1.1, 1.2, … all accepted by v1.x parser."""
    for v in ("1.0", "1.1", "1.5", "1.99"):
        cred = f"sk-fake-{v}"
        item = PoolItem.model_validate({
            "schema_version": v,
            "provider": "gpt",
            "auth_type": "apikey",
            "credential": cred,
            "credential_hash": canonical_hash("gpt", "apikey", cred),
            "source": _src().model_dump(),
        })
        assert item.schema_version == v
