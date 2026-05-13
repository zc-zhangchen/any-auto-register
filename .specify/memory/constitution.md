<!--
Sync Impact Report
==================
Version change: (initial) → 1.0.0
Bump rationale: MAJOR — first ratified constitution; establishes the six load-bearing
principles that govern the upstream registrar (any-auto-register) and its delivery
contract to the downstream KleinAI / gpt2apiup gateway.

Modified principles: (none — initial drafting)
Added sections:
  - Core Principles I–VI
  - Technical Standards
  - Development Workflow
  - Governance

Removed sections: (none)

Templates requiring updates:
  - .specify/templates/plan-template.md      ⚠ pending — Constitution Check section
    must reference Principles I–VI explicitly (gates: PoolItem contract present,
    pusher target whitelisted, provider declared in downstream model, idempotency
    test fixture, e2e fixture, credential at-rest encryption).
  - .specify/templates/spec-template.md      ⚠ pending — add a "Downstream Impact"
    subsection so each spec declares which downstream provider/auth_type it touches.
  - .specify/templates/tasks-template.md     ⚠ pending — categorize tasks under
    upstream / contract / downstream / e2e so Principle VI's gate is mechanical.
  - .specify/templates/checklist-template.md ✅ no change required.
  - .specify/extensions.yml                  ✅ no change required (hooks already
    enforce auto-commit between phases).
  - README.md / docs/                        ⚠ pending — add a link from project
    README to .specify/memory/constitution.md so contributors can find the rules.

Follow-up TODOs:
  - TODO(RUNTIME_GUIDANCE): once SPEC-001 (PoolItem) merges, link its contract
    file from this constitution as the canonical source of truth.
-->

# Any-Auto-Register Constitution

> Scope: **upstream registrar** (`any-auto-register/`, Python) that produces
> verified accounts and delivers them to the **downstream gateway**
> (`gpt2apiup/` KleinAI, Go) via a single import API. All rules below bind both
> sides of the contract; downstream-only changes that touch the contract MUST
> be ratified here first.

## Core Principles

### I. Pool Item Contract First (NON-NEGOTIABLE)

The upstream and downstream MUST communicate exclusively through a versioned
`PoolItem` JSON schema. Upstream code MUST NOT issue SQL against the downstream
database, MUST NOT reach into downstream Redis, and MUST NOT depend on
downstream Go types. The schema lives in two mirrored implementations
(Python `pydantic` upstream, Go `dto` downstream) and is updated by amending
this constitution and SPEC-001 in lockstep.

**Rationale**: Two languages, two release cadences, and two production
deployments cannot share a database; a frozen wire contract is the only way
to evolve them independently without coordinated outages.

### II. Single Downstream Channel (NON-NEGOTIABLE)

The only mechanism by which upstream pushes accounts into the downstream pool
is `POST /admin/api/v1/accounts/import` (or its successors negotiated through
SPEC amendments). No `INSERT` shortcuts, no message queues bypassing the
handler, no per-platform side channels. New delivery targets (file export,
generic webhooks) MUST go through the Pusher abstraction (SPEC-004) and MUST
emit the same `PoolItem` JSON.

**Rationale**: A single ingress is the only place where downstream can enforce
authentication, rate limits, idempotency, audit, and AES-256-GCM encryption.

### III. Credential Confidentiality End-to-End (NON-NEGOTIABLE)

Account credentials (cookies, refresh tokens, passwords, API keys) MUST be
encrypted at rest on the upstream side, transmitted only over HTTPS with a
short-lived Admin JWT, and re-encrypted by the downstream with
AES-256-GCM (`KLEIN_AES_KEY`) before any disk write. Plaintext credentials
MUST NOT appear in logs, error messages, task event payloads, or WebSocket
broadcasts. SSO/refresh tokens MUST NOT be committed to any git repository.

**Rationale**: A leaked sso_*.txt or a log line containing a refresh_token
is a multi-platform compromise. Defense in depth is the only acceptable
posture for a credential-aggregation system.

### IV. Provider Registry Discipline

Every supported provider MUST be declared in three places before its first
production push:

1. Downstream `internal/model/account.go` — provider constant.
2. Downstream `internal/provider/factory/factory.go` — factory entry
   (Mock implementation acceptable for staged rollout).
3. Upstream `core/pools/adapters/<provider>_adapter.py` — `PoolItem` mapper.

String literals representing a provider MUST NOT appear outside these three
files. Adding a provider is a SPEC-level change (minor amendment to this
constitution acceptable; full SPEC required for the new adapter).

**Rationale**: Magic strings sprawl into 40 callsites within one quarter;
the registry forces every new platform to land its contract before any
business code references it.

### V. Idempotency & Retry Safety

Every PoolItem MUST carry enough identity (`credential_hash` derived from
the canonical credential) for the downstream to deduplicate. Upstream
Pusher MUST treat HTTP 2xx with `skipped > 0` as success, MUST NOT panic
on duplicates, MUST retry transient failures with exponential backoff (max
5 attempts), and MUST persist every push attempt in `push_logs` with
correlation to the originating task. The Orchestrator (SPEC-006) MUST
classify task failures into a closed set of categories so that
retry-vs-mark-dead is decided by code, not by humans.

**Rationale**: Batch registration without idempotency is a duplicate
disaster the day Pusher returns 502; without retry classification, a
single transient proxy outage burns a hundred prepaid mailbox slots.

### VI. End-to-End Done Definition (NON-NEGOTIABLE)

No spec is "done" until a single executable test exercises:
`task trigger → PoolItem materialized → Pusher delivers → downstream
accounts row visible → downstream business endpoint serves a request
backed by that account`. Unit tests count toward quality; only the
end-to-end path counts toward completion. Skipping this gate is
permitted only when the spec is explicitly contract-only (e.g.,
SPEC-001 has no business endpoint to exercise) and the deferral is
recorded in `tasks.md` with a follow-up issue.

**Rationale**: Each of the four layers (registrar, pool service,
pusher, downstream provider) has independently worked in past attempts
while the chain remained broken. The contract is the chain, not any
single link.

## Technical Standards

- **Upstream stack**: Python 3.11+, FastAPI, SQLite (default) with an
  explicit migration path to Postgres; React 18 + Vite for the operator UI.
- **Downstream stack**: Go 1.24, Gin, GORM, MySQL 8, Redis. Upstream MUST NOT
  pin downstream minor versions; integration is through the JSON contract only.
- **OpenAI Compatibility (downstream)**: `/v1/*` request/response field names
  on the downstream gateway follow the OpenAI specification verbatim. This
  constitution does not authorize the upstream to invent new `/v1/*` fields.
- **Plugin model (upstream)**: every platform under `platforms/<name>/`
  exposes a `plugin.py` registered via `core/registry.py`, a
  `manifest.yaml` declaring required assets and produced fields, and (once
  SPEC-003 lands) a `PoolItem` adapter under `core/pools/adapters/`.
- **Asset isolation**: email, proxy, phone, CDK, and card pools are managed
  by a single `core/assets/` module (SPEC-005). Per-platform pool files are
  legacy and will be migrated, not extended.
- **Observability**: every task emits structured events on a single
  WebSocket channel (SPEC-006); ad-hoc print statements are not a substitute
  for the event bus and MUST NOT carry credential material.

## Development Workflow

- **Spec-driven**: every non-trivial change starts as a `specs/NNN-name/`
  directory produced by `/speckit-specify`, refined by `/speckit-clarify`,
  planned by `/speckit-plan`, decomposed by `/speckit-tasks`, and only then
  executed by `/speckit-implement`. Drive-by code changes are restricted
  to typo fixes, dependency bumps that pass CI, and reverts.
- **Branch naming**: `NNN-short-slug` matches the spec directory name; the
  speckit git extension creates and validates these.
- **PR review**: every PR links its spec directory and ticks the
  Constitution Check section of `plan.md`. PRs that violate Principle I,
  II, III, or VI are blocked, not negotiated.
- **Auto-commit hooks** (`.specify/extensions.yml`) are kept on; if a hook
  blocks a commit, the underlying issue is fixed rather than bypassed.
- **CI gates** (when configured): upstream `pytest` + `ruff`, downstream
  `go vet ./... && go test ./...`, and the SPEC-008 e2e harness once it
  lands. A red CI bar is not a "known flake"; root-cause it.

## Governance

This constitution supersedes ad-hoc conventions in `CLAUDE.md`, individual
plugin READMEs, and prior planning documents. In any conflict, the
constitution wins; the conflicting document is amended in the same PR.

**Amendment procedure**: open a PR that (a) edits this file, (b) bumps
the version per the rules below, (c) updates the Sync Impact Report
comment at the top, and (d) updates every template/doc flagged as
"⚠ pending" in that report. Amendments are approved by the project
owner before merge; an approval comment that cites the bumped version
counts as ratification.

**Versioning policy** (semver applied to governance):
- **MAJOR** — a non-negotiable principle is removed, redefined, or its
  scope materially narrowed; or the wire contract (Principle I) gains a
  backward-incompatible change.
- **MINOR** — a new principle or section is added, or an existing
  principle gains a new normative clause.
- **PATCH** — wording, examples, references, or links are clarified
  without changing meaning.

**Compliance review**: every spec's `plan.md` Constitution Check section
enumerates Principles I–VI and marks each as `PASS` / `JUSTIFIED` /
`VIOLATION`. A `VIOLATION` blocks the spec from moving past
`/speckit-plan`; a `JUSTIFIED` requires a `Complexity Tracking` row in
the same plan.

**Runtime guidance**: contributors building new platform plugins or
adapters consult `docs/specs/001-poolitem/` (the canonical contract once
SPEC-001 merges) and `platforms/_template/` (the scaffold once SPEC-007
merges). Until those land, this file plus the plan in
`docs/specs/0XX-*.md` is authoritative.

**Version**: 1.0.0 | **Ratified**: 2026-05-13 | **Last Amended**: 2026-05-13
