#!/usr/bin/env bash
# Sync the authoritative PoolItem golden-samples fixture from the contracts
# directory into tests/pools/fixtures/ and verify SHA-256 byte-equality.
#
# Authoritative source:
#   specs/001-poolitem-contract/contracts/golden-samples.jsonl
# Mirror (consumed by pytest):
#   tests/pools/fixtures/golden-samples.jsonl
#
# Exit codes:
#   0 — sync successful, hashes match
#   1 — source missing or copy failed
#   2 — SHA-256 mismatch after copy (should be unreachable)
#
# Repeatable: re-running is idempotent.

set -euo pipefail

# Resolve repo root assuming this script lives in scripts/
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SRC="specs/001-poolitem-contract/contracts/golden-samples.jsonl"
DST_DIR="tests/pools/fixtures"
DST="$DST_DIR/golden-samples.jsonl"

if [[ ! -f "$SRC" ]]; then
    echo "ERROR: authoritative source not found: $SRC" >&2
    exit 1
fi

mkdir -p "$DST_DIR"
cp "$SRC" "$DST"

# Cross-platform SHA-256 (macOS shasum vs Linux sha256sum)
if command -v sha256sum >/dev/null 2>&1; then
    SRC_SHA=$(sha256sum "$SRC" | awk '{print $1}')
    DST_SHA=$(sha256sum "$DST" | awk '{print $1}')
else
    SRC_SHA=$(shasum -a 256 "$SRC" | awk '{print $1}')
    DST_SHA=$(shasum -a 256 "$DST" | awk '{print $1}')
fi

if [[ "$SRC_SHA" != "$DST_SHA" ]]; then
    echo "ERROR: SHA-256 mismatch after copy" >&2
    echo "  src: $SRC_SHA  ($SRC)" >&2
    echo "  dst: $DST_SHA  ($DST)" >&2
    exit 2
fi

echo "OK  golden-samples.jsonl  sha256=$SRC_SHA"
