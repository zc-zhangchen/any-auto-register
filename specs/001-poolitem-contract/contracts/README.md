# PoolItem Contract — Authoritative Source

This directory is the **single source of truth** for the PoolItem wire
contract between the upstream `any-auto-register` (Python) and the
downstream `gpt2apiup` (Go) gateway. Every other file (pydantic models,
Go structs, fixture mirrors) is a derivative or consumer of these files.

## Files

| File | Role |
|------|------|
| `poolitem.schema.json`         | JSON Schema 2020-12 for a single PoolItem; the wire-format contract |
| `poolitem-batch.schema.json`   | JSON Schema for the two batch envelopes (`lines` / `sub2api`) |
| `import-result.schema.json`    | JSON Schema for the downstream `POST /admin/api/v1/accounts/import` response |
| `golden-samples.jsonl`         | 20 hand-curated PoolItem cases used for byte-level cross-language verification |

## Modification protocol

Anything in this directory is **contract surface**. Treat it as
immutable except through a deliberate amendment:

1. Open a SPEC PR that edits the relevant schema files together with
   `spec.md` and `data-model.md` (they are co-authoritative — schemas
   for machines, prose for humans). If the change is non-trivial,
   amend `.specify/memory/constitution.md` first (see Principle I).
2. After updating `golden-samples.jsonl`, rerun
   `scripts/sync_poolitem_fixtures.sh` from the repo root to refresh
   the upstream test mirror (`tests/pools/fixtures/golden-samples.jsonl`).
3. Recompute `credential_hash` for every affected sample with
   `core/pools/canonical.canonical_hash` (do **not** hand-edit hashes).
4. Manually copy the file to the downstream repo at
   `~/Projects/gpt2apiup/backend/internal/dto/testdata/golden-samples.jsonl`
   (until cross-repo automation lands — see T020 / T028).
5. Re-run `pytest tests/pools/` upstream and
   `go test ./internal/dto/...` downstream; both MUST stay green.

## Cross-repo fixture sync rule

The same `golden-samples.jsonl` MUST exist in three byte-identical
copies:

```
specs/001-poolitem-contract/contracts/golden-samples.jsonl   ← authoritative
tests/pools/fixtures/golden-samples.jsonl                    ← upstream mirror
~/Projects/gpt2apiup/backend/internal/dto/testdata/...       ← downstream mirror
```

SHA-256 across all three MUST match. The upstream mirror is enforced by
`scripts/sync_poolitem_fixtures.sh`; the downstream mirror is enforced
by `go test ./internal/dto/...` checksumming the file at decode time
(see SPEC-001 T022, future SPEC-002 CI integration).

## Compatibility envelope (`schema_version`)

- Current production: `1.0`.
- A `1.x` parser MUST accept any minor bump (`1.1`, `1.2`, …) and
  preserve unknown fields verbatim (`extra='allow'` on the Python side,
  `map[string]json.RawMessage` on the Go side).
- A `2.x` payload MUST be rejected with error code
  `invalid_schema_version` until the contract is re-ratified
  (constitution MAJOR bump).

## References

- `research.md` R5 — fixture-sync rationale and historical alternatives
  considered (per-repo regeneration vs single source of truth).
- `spec.md` FR-002, FR-005, FR-008, FR-011, FR-017 — the requirements
  this contract encodes.
- `.specify/memory/constitution.md` Principle I — PoolItem Contract First.
