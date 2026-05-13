"""Shared pytest fixtures for the PoolItem contract test suite.

Both fixtures load the golden-samples.jsonl mirror under
``tests/pools/fixtures/`` (kept in sync with the authoritative source under
``specs/001-poolitem-contract/contracts/`` via
``scripts/sync_poolitem_fixtures.sh``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_FILE = FIXTURES_DIR / "golden-samples.jsonl"


def _iter_raw_lines() -> list[bytes]:
    if not GOLDEN_FILE.exists():
        raise FileNotFoundError(
            f"Missing fixture: {GOLDEN_FILE}. Run scripts/sync_poolitem_fixtures.sh first."
        )
    lines: list[bytes] = []
    with GOLDEN_FILE.open("rb") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            lines.append(stripped)
    return lines


@pytest.fixture(scope="session")
def golden_samples_raw() -> list[bytes]:
    """Raw bytes per non-empty line of golden-samples.jsonl."""
    return _iter_raw_lines()


@pytest.fixture(scope="session")
def golden_samples(golden_samples_raw: list[bytes]) -> list[dict]:
    """Parsed dict per golden sample, preserving every field including ``_case``."""
    return [json.loads(line.decode("utf-8")) for line in golden_samples_raw]
