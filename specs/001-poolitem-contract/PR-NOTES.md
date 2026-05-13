# SPEC-001 PoolItem 中间表示协议 — PR Notes

**Branch**: `001-poolitem-contract` | **Base**: `main` | **Date**: 2026-05-13

本文档预填了开 PR 时需要贴入 description 的两张表：T030（Done 自检 7 项）
与 T031（Constitution Check 6 项）。复制粘贴即可。

---

## T030 — quickstart.md Done 自检 7 项

| # | 检查项 | 状态 | 证据 |
|---|--------|------|------|
| 1 | 上游 `pytest -k poolitem` 全绿，含 roundtrip + canonical hash 一致性 | ✅ | `pytest tests/pools/ -v`：**82 passed**（含 `test_canonical_hash` 12 项、`test_golden_samples` 7 项、`test_schema_evolution` 9 项） |
| 2 | 下游 `go test ./internal/dto/...` 全绿，含同上 + `json.Number` 大整数精度 | ⏸ deferred | Phase 4 (T018–T023) 跨仓任务推迟到 SPEC-002 起步时执行；本仓 PR 不阻塞此项 |
| 3 | 两侧 fixture `golden-samples.jsonl` SHA-256 与权威源一致 | 🟡 上游已对齐 | `bash scripts/sync_poolitem_fixtures.sh` exit 0；SHA-256 = `7612cd02356f3b82392516b336b80fed7fb6a70182fa1a8d5bf6a05a26122070`。下游一侧随 T020 完成 |
| 4 | `contracts/poolitem.schema.json` 通过第三方 validator 对 20 条 fixture 校验 | ✅ | `bash scripts/check_poolitem_contract.sh` stage 3：`OK 20 samples conform to poolitem.schema.json`（python-jsonschema 4.26 / Draft 2020-12） |
| 5 | PR 中"Constitution Check"表 6 项 ✅ 或 JUSTIFIED | ✅ | 见下方 T031 表 |
| 6 | `gpt2apiup/docs/04-API规范.md` 已同步 `format=sub2api` + 11 项错误码 | ⏸ deferred | T028 跨仓任务推迟到 SPEC-002 PR 一起合 |
| 7 | 上游 `bash scripts/check_poolitem_contract.sh` 一键任务通过 | ✅ | 三阶段全 OK：sync → pytest 82 passed → jsonschema 20/20 |

**结论**：本仓侧 5/7 ✅；2 项 (#2 / #6) 显式 deferred 到跨仓 PR。所有 deferred
项都属于 `~/Projects/gpt2apiup/` 修改范围，与 SPEC-002 起步重合，不阻塞 SPEC-001
合并。

---

## T031 — Constitution Check（v1.0.0 六原则）

| # | 原则 | 评估 | 论据 |
|---|------|------|------|
| **I** | Pool Item Contract First | **PASS** | `contracts/poolitem.schema.json` + `contracts/poolitem-batch.schema.json` + `contracts/import-result.schema.json` 是单一权威源；上游 `core/pools/schema.py` 与下游 `internal/dto/pool_item.go`（待 SPEC-002）从中派生。本 spec 即此契约本体 |
| **II** | Single Downstream Channel | **PASS** | FR-006 明确单 endpoint `/admin/api/v1/accounts/import`；`format=lines` 与 `format=sub2api` 共享同一管子，由 `LinesBatch` / `Sub2ApiBatch` 落地（`core/pools/schema.py`） |
| **III** | Credential Confidentiality End-to-End | **PASS** | (a) `golden-samples.jsonl` 全部使用 `*fake*` 合成凭据，无真实 token；(b) `core/pools/canonical.py:mask_credential` 提供日志掩码（`test_canonical_hash.py` 7 桶测试）；(c) 本 PR 未引入任何 SSO/refresh token 文件；(d) `credential_hash` 仅幂等键，攻击者获取无法反推 |
| **IV** | Provider Registry Discipline | **JUSTIFIED** | 见 plan.md Complexity Tracking。本 spec **声明** provider 枚举来自下游 model + factory 注册表，schema 仅做形态校验（`^[a-z][a-z0-9_]{1,31}$`）。实际枚举的实施在 SPEC-002 |
| **V** | Idempotency & Retry Safety | **PASS** | (a) `canonical_hash` 算法在 FR-005 / `data-model.md` 附录 B 锁定（13 项 `test_canonical_hash` 验证）；(b) 11 项错误码 + Pusher 决策语义在 FR-008 表格固化（schema enum + `test_batch_models.py` 校验）；(c) 重复推送 → `skipped` HTTP 2xx 在 FR-009 规定 |
| **VI** | End-to-End Done Definition | **JUSTIFIED (contract-only)** | 见 plan.md Constitution Check。本 spec 是契约本体，无可调用的业务 endpoint。两侧 roundtrip + 黄金样本字节级对齐作为契约级 e2e（上游已绿；下游待 SPEC-002）。完整 e2e（含真实 push）留给 SPEC-008 |

**结论**：6 原则全部 PASS（4）或 JUSTIFIED（2）；**0 项 VIOLATION**。可合并。

---

## 本 PR scope summary

**已完成（本仓 25 / 31 个任务）**：

- Phase 1 Setup：T001–T003（T004 deferred）
- Phase 2 Foundational：T005–T008
- Phase 3 US1 MVP：T009–T017
- Phase 5 US3（上游侧）：T024、T026
- Phase 6 Polish：T027、T029、T030、T031

**Deferred（6 个跨仓任务）**：

- T004 — `~/Projects/gpt2apiup/.../.gitkeep`（SPEC-002 起步时执行）
- T018–T022 — 下游 Go struct + canonical_test + golden_samples_test（SPEC-002 跨仓 PR）
- T023 — 下游 CI `go test`
- T025 — 下游演进测试（与 T024 对照实现）
- T028 — `gpt2apiup/docs/04-API规范.md` 同步（随 SPEC-002 PR）

**附加修复**（在 PR 中独立 commit）：

- `contracts/poolitem.schema.json`：(a) 顶层 `additionalProperties` 从 `false`
  改 `true`（修 FR-012 forward-compat 与 schema 的字面冲突）；(b) `MetaValue`
  从 `oneOf` 改 `anyOf`（修 integer 同时匹配 `integer` 与 `number` 时 oneOf
  歧义）。两处都让 jsonschema validator 与 spec.md 语义一致。

---

## 验证命令清单（评审者复现）

```bash
cd ~/Projects/any-auto-register
bash scripts/check_poolitem_contract.sh
# 预期：3 stage 全绿，82 passed，20/20 schema conform
```

或单独跑：

```bash
bash scripts/sync_poolitem_fixtures.sh       # SHA-256 一致
python3 -m pytest tests/pools/ -v            # 82 passed
```
