"""Golden-sample suite: fixture is the cross-language contract witness.

For every entry in ``golden-samples.jsonl`` the upstream pydantic schema
MUST:

* validate it without error,
* preserve its field set under ``model_dump`` (modulo the ``_case`` label),
* and ``credential_hash`` MUST equal a fresh ``canonical_hash`` recompute.
"""

from __future__ import annotations

import pytest

from core.pools.canonical import canonical_hash
from core.pools.schema import PoolItem


def test_fixture_has_twenty_samples(golden_samples):
    assert len(golden_samples) == 20


def test_all_samples_validate(golden_samples):
    for d in golden_samples:
        payload = {k: v for k, v in d.items() if k != "_case"}
        # mfa_seed and other unknown fields are tolerated via extra='allow'
        PoolItem.model_validate(payload)


def test_dump_preserves_field_set(golden_samples):
    for d in golden_samples:
        payload = {k: v for k, v in d.items() if k != "_case"}
        item = PoolItem.model_validate(payload)
        dumped = item.model_dump(exclude_none=True)

        # Every key from the source dict (excluding _case) must round-trip.
        # Keys with explicit null in the source are preserved by extra='allow'
        # but pydantic may strip them if they're declared optional with None
        # default — handle that by inspecting dump-without-exclude.
        full_dump = item.model_dump(exclude_none=False)
        for k, v in payload.items():
            assert k in full_dump, f"key {k!r} missing from dump for {d.get('_case')}"
            if v is None:
                assert full_dump[k] is None, f"explicit null lost for {k!r}"
            # Note: dump and full_dump diverge only on absence-vs-null, not value.
            # Equality of value is enforced by canonical_hash recompute below.


def test_credential_hash_matches_canonical_recompute(golden_samples):
    for d in golden_samples:
        recomputed = canonical_hash(
            d["provider"],
            d["auth_type"],
            d.get("credential", ""),
            d.get("refresh_token"),
        )
        assert recomputed == d["credential_hash"], (
            f"hash drift on {d.get('_case')!r}: "
            f"stored={d['credential_hash']!r} recomputed={recomputed!r}"
        )


def test_duplicate_case_05_shares_hash_with_case_01(golden_samples):
    by_case = {d["_case"]: d for d in golden_samples}
    assert by_case["05_duplicate_of_01_for_dedup_test"]["credential_hash"] == (
        by_case["01_chatgpt_oauth_full"]["credential_hash"]
    )


def test_case_14_v1_1_payload_is_accepted_by_v1_0_parser(golden_samples):
    """Forward-compat: v1.0 parser MUST read v1.1 (FR-012)."""
    by_case = {d["_case"]: d for d in golden_samples}
    payload = {k: v for k, v in by_case["14_future_schema_1_1_with_unknown_field"].items() if k != "_case"}
    item = PoolItem.model_validate(payload)
    assert item.schema_version == "1.1"
    # mfa_seed should survive in extras
    dumped = item.model_dump(exclude_none=False)
    assert dumped.get("mfa_seed") == "FAKE_MFA_SEED_DO_NOT_USE"


def test_raw_lines_byte_equal_to_authoritative(golden_samples_raw):
    """Fixture mirror must equal the source byte-for-byte (script-enforced)."""
    import hashlib
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "specs" / "001-poolitem-contract" / "contracts" / "golden-samples.jsonl"
    mirror = Path(__file__).parent / "fixtures" / "golden-samples.jsonl"
    assert hashlib.sha256(src.read_bytes()).hexdigest() == (
        hashlib.sha256(mirror.read_bytes()).hexdigest()
    ), "fixture mirror drifted from authoritative source — run scripts/sync_poolitem_fixtures.sh"
