"""Map a Grok account record to a PoolItem.

This is the **reference adapter**. New platform plugins should copy this
shape: one ``to_pool_item`` function that takes the platform-native
account object plus task provenance kwargs and returns a validated
:class:`PoolItem`. No HTTP, no DB, no Pusher.

Grok produces cookie-based credentials (the ``sso`` cookie value);
nothing about the OAuth or apikey paths applies here.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..canonical import canonical_hash
from ..schema import PoolItem, PoolItemSource

PROVIDER = "grok"
AUTH_TYPE = "cookie"


class GrokAccountLike(Protocol):
    """Structural type for the minimum surface a Grok account exposes.

    Real callsites pass in the upstream platform plugin's account model;
    duck-typing via Protocol keeps the adapter decoupled from any single
    concrete class.
    """

    sso: str  # raw cookie value (e.g. "eyJfake.sso.grok.XX")
    email: str | None
    expires_at: str | None
    proxy_hint: str | None


def to_pool_item(
    account: GrokAccountLike | Any,
    *,
    task_id: str,
    registered_at: str,
    executor: str,
    registrar_version: str | None = None,
    weight: int | None = None,
    meta: dict[str, Any] | None = None,
) -> PoolItem:
    """Map a Grok account into a validated :class:`PoolItem`.

    The ``credential_hash`` field is computed by this adapter — callers
    MUST NOT pre-fill it.
    """
    sso = getattr(account, "sso", None)
    if not sso:
        raise ValueError("grok account is missing a non-empty sso cookie")

    cred_hash = canonical_hash(PROVIDER, AUTH_TYPE, sso)

    source = PoolItemSource(
        task_id=task_id,
        registered_at=registered_at,
        executor=executor,  # type: ignore[arg-type]
        registrar_version=registrar_version,
    )

    return PoolItem(
        schema_version="1.0",
        provider=PROVIDER,
        auth_type=AUTH_TYPE,
        credential=sso,
        credential_hash=cred_hash,
        email=getattr(account, "email", None),
        weight=weight,
        proxy_hint=getattr(account, "proxy_hint", None),
        expires_at=getattr(account, "expires_at", None),
        meta=meta,
        source=source,
    )
