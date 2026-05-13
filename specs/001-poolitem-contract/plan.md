# Implementation Plan: PoolItem 中间表示协议

**Branch**: `001-poolitem-contract` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-poolitem-contract/spec.md`

## Summary

把上下游账号载荷的字段、序列化格式、错误码、版本演进规则**作为契约固化**，落地为两份镜像实现（Python pydantic v2 + Go struct）+ 一份权威 JSON Schema + 一份跨语言黄金样本（jsonl）。本 spec **不实现** Pusher / 下游 provider 扩容 / 加密入库——这些分别由 SPEC-002 / SPEC-003 / SPEC-004 承担。本 spec 的"完成"等价于：两侧实现各自跑通 roundtrip 测试，且对同一份黄金样本字节级一致。

技术路线：以 `specs/001-poolitem-contract/contracts/` 为契约权威源；上游 `core/pools/schema.py` 与下游 `internal/dto/pool_item.go` 各自从中派生，CI 检查双侧 fixture 与契约源一致。

## Technical Context

**Language/Version**: Python 3.11+ (upstream)；Go 1.24 (downstream)

**Primary Dependencies**:
- 上游：pydantic v2 (`>= 2.7`)、`hashlib` (stdlib)
- 下游：标准库 `encoding/json` + `crypto/sha256`；JSON 数值精度使用 `json.Number` 解码以保留 int64 > 2^53
- 契约：JSON Schema draft 2020-12（人类可读 + 第三方校验工具兼容）

**Storage**: N/A — 本 spec 不写库；下游入库 schema 已存在（`internal/model/account.go`），由 SPEC-002 扩 enum 时再迁移

**Testing**:
- 上游：`pytest` + `pytest-golden`（roundtrip + canonical hash 一致性）
- 下游：`go test ./internal/dto/...`（同上）
- 跨语言：CI 在两个仓库各跑一次，对 `contracts/golden-samples.jsonl` 字节级 SHA-256 比较

**Target Platform**: 跨语言 JSON-over-HTTPS 契约（部署侧均为 Linux server）

**Project Type**: web-service（双仓库 dual-stack：any-auto-register Python + gpt2apiup Go）

**Performance Goals**:
- 单条 PoolItem 序列化 / 反序列化 P95 < 1ms（不含 IO）
- 100 条批次双向 roundtrip < 50ms 单语言
- 与 SC-006 一致：端到端（adapter → push → import → query）P95 ≤ 2s

**Constraints**:
- 不引入新的运行时 HTTP 依赖（pydantic / encoding/json 已是各自栈的默认选择）
- `meta` 嵌套深度 ≤ 4，避免递归校验栈溢出
- 单批次 ≤ 500 PoolItem（FR-010 强约束）
- 不在传输层做二次加密（FR-014）

**Scale/Scope**:
- 首批 6 个 provider（chatgpt / grok / kiro / cursor / openblocklabs / tavily）
- 预期一年内增长至 10-15
- 单实例日推送量预期上限 10k 条（远低于批次上限聚合）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

按宪法 v1.0.0 六条原则逐项检查：

| # | 原则 | 检查项 | 评估 |
|---|---|---|---|
| **I** | Pool Item Contract First | 本 spec 是否定义了独立的 PoolItem JSON 契约？是否避免了上游直连下游 DB？ | **PASS** — 本 spec 即为该契约本体；FR-001~FR-018 是契约条款 |
| **II** | Single Downstream Channel | 是否只通过 `/admin/api/v1/accounts/import` 投递？是否禁止第二通道？ | **PASS** — FR-006 明确 HTTPS + Admin JWT 走单一入口；`format=lines` 与 `sub2api` 都走同一 endpoint |
| **III** | Credential Confidentiality | 凭据是否仅 TLS 传输？日志是否掩码？是否不入 git？ | **PASS** — FR-014/015 codify；契约样本中所有 token 字段使用合成值，非真实凭据 |
| **IV** | Provider Registry Discipline | provider 字段是否走注册表？是否避免散落字符串？ | **JUSTIFIED** — 本 spec **声明** provider 枚举来自下游注册表，但**不**实施新 provider 注册（那是 SPEC-002 的范围）；本 spec 完成时下游可接受的 provider 仍为现有 `gpt\|grok`，不破坏 IV 的字面要求 |
| **V** | Idempotency & Retry Safety | 是否定义幂等键？是否定义重试分类？ | **PASS** — FR-005 `credential_hash` 是幂等键；FR-008 的 11 项错误码 + Pusher 决策表是重试分类的契约 |
| **VI** | End-to-End Done Definition | 是否有端到端用例可验证？ | **JUSTIFIED (contract-only)** — 本 spec 没有业务 endpoint 可调用，但提供两侧 roundtrip 测试 + 黄金样本对齐作为契约级 e2e；完整 e2e（含真实 push）留给 SPEC-008 |

**初始 Constitution Check 结论**：6/6 项 PASS 或 JUSTIFIED；进入 Phase 0。

### Phase 1 后复检

| # | 原则 | 复检结论 |
|---|---|---|
| I | Pool Item Contract First | **PASS** — `contracts/poolitem.schema.json` 是单一权威源 |
| II | Single Downstream Channel | **PASS** — `contracts/poolitem-batch.schema.json` 把两个 format 都收敛到 `/admin/api/v1/accounts/import` 请求体内 |
| III | Credential Confidentiality | **PASS** — `quickstart.md` 含掩码日志示例；`golden-samples.jsonl` 中凭据为可识别假值（`sk-fake-*`、`eyJfake.*`） |
| IV | Provider Registry Discipline | **JUSTIFIED** — schema enum 中 `provider` 列出 6 个名称但解析方按"下游已注册集合"裁剪；不破坏 IV |
| V | Idempotency & Retry Safety | **PASS** — schema 含 `credential_hash` 必填校验 + `errors[].code` 枚举校验 |
| VI | End-to-End Done Definition | **PASS (contract-level)** — Phase 1 输出含跨语言 roundtrip 黄金样本 |

## Project Structure

### Documentation (this feature)

```text
specs/001-poolitem-contract/
├── plan.md              # This file
├── spec.md              # Already exists (input)
├── research.md          # Phase 0 output（本次产出）
├── data-model.md        # Phase 1 output（本次产出）
├── quickstart.md        # Phase 1 output（本次产出）
├── contracts/           # Phase 1 output（本次产出）
│   ├── poolitem.schema.json
│   ├── poolitem-batch.schema.json
│   ├── import-result.schema.json
│   └── golden-samples.jsonl
├── checklists/
│   └── requirements.md  # Already exists
└── tasks.md             # NOT created here（/speckit-tasks 之后）
```

### Source Code (when /speckit-implement runs)

**Project Type**: dual-repository web-service（两个独立仓库，通过 JSON 契约耦合）。

```text
# 上游 — any-auto-register（Python，本仓库）
any-auto-register/
├── core/
│   └── pools/
│       └── schema.py                    # pydantic v2 模型
└── tests/
    └── pools/
        ├── test_poolitem_schema.py      # 字段校验 + canonical hash
        ├── test_golden_samples.py       # 加载 jsonl 做双向往返
        └── fixtures/
            └── golden-samples.jsonl     # 从 specs/.../contracts/ 同步

# 下游 — gpt2apiup（Go，外部仓库）
gpt2apiup/backend/internal/dto/
├── pool_item.go                          # struct + json tag
├── pool_item_test.go                     # 同上 roundtrip
└── testdata/
    └── golden-samples.jsonl              # 从 specs/.../contracts/ 同步
```

**Structure Decision**: 契约本体放在 `specs/001-poolitem-contract/contracts/` 作为单一权威源（git 版本化、人类可读）。两个仓库的 fixture 都从这里同步（首版手工，SPEC-008 引入跨仓库 CI 时改为脚本驱动）。这种"权威源 + 两份 fixture"模式比"放进任一仓库"更中立，且方便 PR 评审契约变更。

## Complexity Tracking

> 仅在 Constitution Check 有 violation 需要 justify 时填写。本 spec 无 violation，仅有两条 JUSTIFIED 项：

| Item | Why Justified | Simpler Alternative Rejected Because |
|------|---------------|--------------------------------------|
| Principle IV: provider 枚举不在本 spec 完整列出 | 真正落地需要先在下游 model + factory 注册（SPEC-002 范围）；本 spec 完成时仍只识别 `gpt\|grok`，但 schema 已允许扩展 | "本 spec 一次性列全 6 个 provider"会让上游 schema 与下游能力不对齐——上游写出 `provider=kiro` 推送时下游会 400，破坏 SC-003 |
| Principle VI: 无业务 endpoint 端到端测试 | 本 spec 是契约本体，没有可调用的业务接口；e2e 工具链在 SPEC-008 才完整 | "等 SPEC-008 一起做"会让契约 6 个月内不冻结，后续 7 份 spec 全部悬空，违背 SpecKit 的分层依赖原则 |
