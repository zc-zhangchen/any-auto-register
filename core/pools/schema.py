"""Pydantic v2 models for the PoolItem wire contract.

These six models mirror the entities in
``specs/001-poolitem-contract/data-model.md`` and the JSON Schemas under
``specs/001-poolitem-contract/contracts/``. JSON field names and the
optional/required boundary are byte-for-byte aligned with the Go
counterpart (``~/Projects/gpt2apiup/backend/internal/dto/``) so that the
same ``golden-samples.jsonl`` round-trips on both sides.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .canonical import canonical_hash


_AUTH_TYPES = ("cookie", "oauth", "apikey")
_EXECUTORS = ("protocol", "headless", "headed")
_MAX_META_DEPTH = 4


def _meta_depth(value: Any) -> int:
    """Maximum container-nesting depth of a JSON value.

    Scalars (str / int / float / bool / None) → 0.
    Each enclosing dict or list adds 1. So ``{"a": "x"}`` is depth 1,
    ``{"a": {"b": "x"}}`` is depth 2, etc. Empty containers count as 1.
    """
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(_meta_depth(v) for v in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_meta_depth(v) for v in value)
    return 0


class PoolItemSource(BaseModel):
    """Provenance / registration trace for a PoolItem."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: str = Field(min_length=1, max_length=64)
    registered_at: str
    executor: Literal["protocol", "headless", "headed"]
    registrar_version: str | None = Field(default=None, max_length=32)


class PoolItem(BaseModel):
    """Standardised payload describing one registered account.

    Forward-compatible: unknown fields are preserved via ``extra='allow'``
    so a v1.0 parser can read a v1.1 payload without failing (FR-012).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = "1.0"
    provider: str
    auth_type: Literal["cookie", "oauth", "apikey"]
    credential: str = ""
    credential_hash: str = Field(min_length=64, max_length=64)
    access_token: str | None = None
    refresh_token: str | None = None
    email: str | None = Field(default=None, max_length=254)
    weight: int | None = Field(default=None, ge=1, le=10000)
    proxy_hint: str | None = None
    expires_at: str | None = None
    region: str | None = Field(default=None, max_length=32)
    meta: dict[str, Any] | None = None
    source: PoolItemSource

    @field_validator("credential_hash")
    @classmethod
    def _hash_is_lower_hex(cls, v: str) -> str:
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
            raise ValueError("credential_hash must be 64 lowercase hex chars")
        return v

    @field_validator("schema_version")
    @classmethod
    def _schema_version_form(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(f"schema_version must be MAJOR.MINOR, got {v!r}")
        if int(parts[0]) >= 2:
            raise ValueError(
                f"schema_version {v!r} not supported by 1.x parser (invalid_schema_version)"
            )
        return v

    @model_validator(mode="after")
    def _check_auth_type_credentials(self) -> "PoolItem":
        """Cross-field auth_type / credential rules (data-model.md Entity 1)."""
        at = self.auth_type
        cred = (self.credential or "").strip()

        if at == "cookie":
            if not cred:
                raise ValueError(
                    "auth_type='cookie' requires non-empty credential (field='credential')"
                )
        elif at == "apikey":
            if not cred:
                raise ValueError(
                    "auth_type='apikey' requires non-empty credential (field='credential')"
                )
        elif at == "oauth":
            access = (self.access_token or "").strip()
            refresh = (self.refresh_token or "").strip()
            if not (cred or access or refresh):
                raise ValueError(
                    "auth_type='oauth' requires at least one of "
                    "credential / access_token / refresh_token (field='credential')"
                )
        return self

    @model_validator(mode="after")
    def _check_meta_depth(self) -> "PoolItem":
        if self.meta is None:
            return self
        depth = _meta_depth(self.meta)
        if depth > _MAX_META_DEPTH:
            raise ValueError(
                f"meta nesting depth {depth} exceeds max {_MAX_META_DEPTH} (field='meta')"
            )
        return self

    @model_validator(mode="after")
    def _check_credential_hash(self) -> "PoolItem":
        """credential_hash MUST equal canonical_hash(provider, auth_type, ...)."""
        expected = canonical_hash(
            self.provider,
            self.auth_type,
            self.credential or "",
            self.refresh_token,
        )
        if self.credential_hash != expected:
            raise ValueError(
                "credential_hash mismatch: expected "
                f"{expected!r} from canonical_hash(...) (field='credential_hash')"
            )
        return self


class LinesBatch(BaseModel):
    """``format='lines'`` batch envelope (compat with register-to-pool)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    format: Literal["lines"]
    provider: str
    auth_type: Literal["cookie", "oauth", "apikey"]
    text: str = Field(min_length=1)
    proxy_id: int | None = None
    weight: int | None = Field(default=None, ge=1, le=10000)

    @model_validator(mode="after")
    def _text_has_non_blank_line(self) -> "LinesBatch":
        kept = [
            line for line in self.text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not kept:
            raise ValueError("text must contain at least one non-empty, non-comment line")
        if len(kept) > 500:
            raise ValueError(f"text expands to {len(kept)} lines, max 500 (batch_too_large)")
        return self


class Sub2ApiBatch(BaseModel):
    """``format='sub2api'`` batch envelope carrying structured PoolItems."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    format: Literal["sub2api"]
    accounts: list[PoolItem] = Field(min_length=1, max_length=500)
    proxy_id: int | None = None
    default_weight: int | None = Field(default=None, ge=1, le=10000)


class ImportError(BaseModel):
    """One entry in :class:`ImportResult.errors`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    index: int = Field(ge=0)
    code: str
    message: str
    field: str | None = None


class ImportResult(BaseModel):
    """Downstream response body for ``POST /admin/api/v1/accounts/import``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    imported: int = Field(ge=0)
    skipped: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: list[ImportError] | None = None
    request_id: str | None = None

    @model_validator(mode="after")
    def _errors_invariant(self) -> "ImportResult":
        # errors MUST be present when failed > 0; MUST be empty or absent when failed == 0
        if self.failed > 0 and not self.errors:
            raise ValueError("errors must be non-empty when failed > 0")
        if self.failed == 0 and self.errors:
            raise ValueError("errors must be empty or absent when failed == 0")
        return self
