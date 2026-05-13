"""Canonical hash + masking helpers for PoolItem.

Reference implementation lives in specs/001-poolitem-contract/data-model.md
附录 A / B. Both the Python (here) and Go (downstream) implementations MUST
produce byte-identical output for the same inputs; golden-samples.jsonl is
the cross-language verification fixture.
"""

from __future__ import annotations

import hashlib


def canonical_hash(
    provider: str,
    auth_type: str,
    credential: str,
    refresh_token: str | None = None,
) -> str:
    """Return the canonical SHA-256 hex digest of a credential triple.

    Algorithm (spec.md FR-005):
        c = strip(credential) or strip(refresh_token or "")
        payload = lower(provider) + "\\n" + lower(auth_type) + "\\n" + c
        return sha256(payload).hexdigest()

    Returns a 64-character lowercase hex string.
    """
    if provider is None or auth_type is None:
        raise ValueError("provider and auth_type are required for canonical_hash")

    c = (credential or "").strip()
    if not c:
        c = (refresh_token or "").strip()

    payload = f"{provider.lower()}\n{auth_type.lower()}\n{c}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def mask_credential(s: str) -> str:
    """Return a log-safe masked representation of a credential.

    Mirrors the Go implementation in data-model.md 附录 A. Rule:
        len < 4   → '…'
        len < 12  → first…last
        otherwise → first4…last4
    """
    if not s:
        return "…"
    n = len(s)
    if n < 4:
        return "…"
    if n < 12:
        return f"{s[0]}…{s[-1]}"
    return f"{s[:4]}…{s[-4:]}"
