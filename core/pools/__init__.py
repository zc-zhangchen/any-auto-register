"""PoolItem 中间表示协议 — 上下游账号载荷统一 JSON 契约。

See ``specs/001-poolitem-contract/`` for the spec, plan, data-model,
schemas, golden samples, and evolution rules. This module is the
authoritative upstream (Python) side of the contract; the downstream
mirror lives in ``~/Projects/gpt2apiup/backend/internal/dto/`` (Go).

Public surface (everything below is part of the contract; downstream
consumers should depend only on these names):
"""

from .canonical import canonical_hash, mask_credential
from .schema import (
    ImportError,
    ImportResult,
    LinesBatch,
    PoolItem,
    PoolItemSource,
    Sub2ApiBatch,
)

__all__ = [
    "PoolItem",
    "PoolItemSource",
    "LinesBatch",
    "Sub2ApiBatch",
    "ImportResult",
    "ImportError",
    "canonical_hash",
    "mask_credential",
]
