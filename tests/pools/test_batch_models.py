"""Tests for the batch envelope and import-response models (T010 outputs)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.pools.canonical import canonical_hash
from core.pools.schema import (
    ImportError as PoolImportError,
    ImportResult,
    LinesBatch,
    PoolItem,
    PoolItemSource,
    Sub2ApiBatch,
)


def _src() -> PoolItemSource:
    return PoolItemSource(
        task_id="t-batch",
        registered_at="2026-05-13T03:14:15Z",
        executor="protocol",
    )


def _item(suffix: str) -> PoolItem:
    cred = f"sk-fake-{suffix}"
    return PoolItem(
        provider="gpt",
        auth_type="apikey",
        credential=cred,
        credential_hash=canonical_hash("gpt", "apikey", cred),
        source=_src(),
    )


class TestLinesBatch:
    def test_minimal_valid(self):
        b = LinesBatch(format="lines", provider="grok", auth_type="cookie", text="eyJfake.sso.01")
        assert b.format == "lines"

    def test_blank_text_rejected(self):
        with pytest.raises(ValidationError):
            LinesBatch(format="lines", provider="grok", auth_type="cookie", text="")

    def test_whitespace_and_comments_only_rejected(self):
        with pytest.raises(ValidationError):
            LinesBatch(
                format="lines",
                provider="grok",
                auth_type="cookie",
                text="\n# a comment\n   \n",
            )

    def test_too_many_lines_rejected(self):
        text = "\n".join(f"eyJfake.sso.{i}" for i in range(501))
        with pytest.raises(ValidationError, match="batch_too_large|max 500"):
            LinesBatch(format="lines", provider="grok", auth_type="cookie", text=text)

    def test_wrong_format_literal(self):
        with pytest.raises(ValidationError):
            LinesBatch(format="sub2api", provider="grok", auth_type="cookie", text="x")  # type: ignore[arg-type]


class TestSub2ApiBatch:
    def test_minimal_valid(self):
        b = Sub2ApiBatch(format="sub2api", accounts=[_item("a")])
        assert b.format == "sub2api"
        assert len(b.accounts) == 1

    def test_empty_accounts_rejected(self):
        with pytest.raises(ValidationError):
            Sub2ApiBatch(format="sub2api", accounts=[])

    def test_too_many_accounts_rejected(self):
        many = [_item(str(i)) for i in range(501)]
        with pytest.raises(ValidationError):
            Sub2ApiBatch(format="sub2api", accounts=many)

    def test_default_weight_range(self):
        with pytest.raises(ValidationError):
            Sub2ApiBatch(format="sub2api", accounts=[_item("w")], default_weight=0)
        with pytest.raises(ValidationError):
            Sub2ApiBatch(format="sub2api", accounts=[_item("w")], default_weight=10001)


class TestImportResult:
    def test_minimal_success(self):
        r = ImportResult(imported=3, skipped=1, failed=0)
        assert r.imported == 3

    def test_negative_counts_rejected(self):
        with pytest.raises(ValidationError):
            ImportResult(imported=-1, skipped=0, failed=0)

    def test_failed_without_errors_rejected(self):
        with pytest.raises(ValidationError, match="errors"):
            ImportResult(imported=0, skipped=0, failed=1)

    def test_errors_without_failures_rejected(self):
        with pytest.raises(ValidationError, match="errors"):
            ImportResult(
                imported=1,
                skipped=0,
                failed=0,
                errors=[PoolImportError(index=0, code="x", message="y")],
            )

    def test_failed_with_errors_ok(self):
        r = ImportResult(
            imported=0,
            skipped=0,
            failed=1,
            errors=[
                PoolImportError(
                    index=0, code="unknown_provider", message="provider not registered", field="provider",
                )
            ],
        )
        assert r.errors and r.errors[0].code == "unknown_provider"


class TestImportError:
    def test_minimal(self):
        e = PoolImportError(index=0, code="missing_required_field", message="m")
        assert e.field is None

    def test_negative_index_rejected(self):
        with pytest.raises(ValidationError):
            PoolImportError(index=-1, code="x", message="m")

    def test_extra_rejected(self):
        with pytest.raises(ValidationError):
            PoolImportError(index=0, code="x", message="m", surprise="z")  # type: ignore[call-arg]
