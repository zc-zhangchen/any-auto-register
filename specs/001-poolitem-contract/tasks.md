# Tasks: PoolItem 中间表示协议

**Input**: Design documents from `/specs/001-poolitem-contract/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: REQUIRED — FR-017 / FR-018 显式要求双语 roundtrip + 黄金样本 CI 校验；本 spec 的 Done 自检 7 项里 4 项是测试。

**Organization**: 按 user story 编排（US1 / US2 / US3 来自 spec.md），每个 story 可独立交付与验证。

## Format

```text
- [ ] [TaskID] [P?] [Story?] Description with file path
```

- **[P]**：任务可并行（不同文件、无未完成依赖）
- **[Story]**：US1 / US2 / US3 仅在 user-story phase 出现
- 路径分两类：
  - 上游本仓 — 相对路径 `core/...` / `tests/...` / `specs/...`
  - 下游外仓 — 绝对路径 `~/Projects/gpt2apiup/backend/...`（开发者自行同步至该仓库）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 项目骨架与目录占位；不引入任何业务代码

- [x] T001 在上游本仓创建 `core/pools/__init__.py`（空 `__all__`），用于挂载 PoolItem 相关模块
- [x] T002 在上游本仓创建 `tests/pools/__init__.py` + `tests/pools/fixtures/.gitkeep`
- [x] T003 [P] 在 `requirements.txt` 追加 `pydantic>=2.7`（若已有则跳过），并在 README 中标注"PoolItem 契约依赖 pydantic v2"
- [x] T004 [P] 在下游外仓创建 `~/Projects/gpt2apiup/backend/internal/dto/testdata/.gitkeep`（如目录已存在则跳过) — *deferred: gpt2apiup repo out of scope for this Ralph run; tracked for SPEC-002 / T020*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 跨 story 共享的契约与 fixture 基础；US1 / US2 / US3 都依赖

- [x] T005 重写 `specs/001-poolitem-contract/contracts/golden-samples.jsonl` 中 20 条样本的 `credential_hash` 字段，使其按 spec.md FR-005 算法**真实计算**（当前 jsonl 中是形态占位 hex，需用 Python 一次性重算并写回；保留每条 `_case` 标签便于追溯）
- [x] T006 创建 `scripts/sync_poolitem_fixtures.sh`：(a) 把权威源 `specs/001-poolitem-contract/contracts/golden-samples.jsonl` 复制到 `tests/pools/fixtures/golden-samples.jsonl`；(b) 计算两份 SHA-256 并 diff，不一致退出码非 0；(c) 在仓库 root 跑可重复
- [x] T007 [P] 在 `tests/pools/conftest.py` 提供两个 pytest fixture：`golden_samples`（list of dict，加载 jsonl）和 `golden_samples_raw`（list of bytes，原始 line）
- [x] T008 [P] 在 `specs/001-poolitem-contract/contracts/README.md` 写一份"权威源说明"：说明此目录是契约本体、修改流程、跨仓 fixture 同步规则；引用 research.md R5

---

## Phase 3: User Story 1 — 上游 adapter 可把 Account 映射为 PoolItem (P1) 🎯 MVP

**Story Goal**：平台插件作者写一个映射函数即可产出合法 PoolItem JSON，无需关心 HTTP / 下游表结构。

**Independent Test**：在上游独立验证——无需启动下游服务；用 grok 现有 Account 实例调 adapter 产出 PoolItem，跑 roundtrip + canonical_hash 一致性。

- [x] T009 [P] [US1] 创建 `core/pools/canonical.py`：实现 `canonical_hash(provider, auth_type, credential, refresh_token=None) -> str` 与 `mask_credential(s) -> str`，对照 data-model.md 附录 A/B 的参考实现
- [x] T010 [P] [US1] 创建 `core/pools/schema.py`：用 pydantic v2 实现 `PoolItemSource` / `PoolItem` / `LinesBatch` / `Sub2ApiBatch` / `ImportError` / `ImportResult` 六个模型；`PoolItem.model_config = ConfigDict(extra='allow')`；字段顺序与 JSON tag 与 data-model.md 一对一
- [x] T011 [US1] 在 `core/pools/schema.py` 的 `PoolItem` 上加 `@model_validator(mode="after")` 校验 `credential_hash` 必须等于 `canonical_hash(...)`，不匹配抛 `ValueError` 含字段名（依赖 T009 / T010）
- [x] T012 [US1] 在 `core/pools/schema.py` 的 `PoolItem` 上加 `@model_validator(mode="after")` 实现 cross-field 校验（auth_type=cookie → credential 必非空；auth_type=oauth → credential/access_token/refresh_token 三选一非空；data-model.md Entity 1 验证规则 1–3）
- [x] T013 [P] [US1] 创建 `core/pools/adapters/__init__.py` + `core/pools/adapters/grok_adapter.py`：实现 `to_pool_item(account: GrokAccount, *, task_id: str, registered_at: str, executor: str) -> PoolItem`；只做映射，**不**做 HTTP。作为新平台接入的样板
- [x] T014 [P] [US1] 创建 `tests/pools/test_canonical_hash.py`：表驱动测试 10+ 组 `(provider, auth_type, credential, refresh_token)` → 预期 64 hex（10 组里至少含：lowercase 验证、trim 验证、refresh_token fallback、空 credential 报错路径）
- [x] T015 [P] [US1] 创建 `tests/pools/test_poolitem_schema.py`：(a) 必填缺失 → ValidationError；(b) auth_type=cookie 但 credential="" → 拒；(c) auth_type=oauth 三 token 全空 → 拒；(d) credential_hash 不匹配 → 拒；(e) meta 嵌套 > 4 层 → 拒；(f) extra 字段保留（forward-compat）
- [x] T016 [US1] 创建 `tests/pools/test_golden_samples.py`：(a) 加载 fixture（依赖 T007），对每条 PoolItem 跑 `model_validate(d)` 不抛错；(b) `model_dump()` 后字段集合 = 原 dict 字段集合（除 `_case` 元字段）；(c) 重算 `credential_hash` = 存储值（依赖 T005 已重算的 fixture）
- [x] T017 [US1] 在 `tests/pools/test_adapter_grok.py` 用一个 mock GrokAccount 验证 grok_adapter 产出的 PoolItem 通过 schema 校验且 `credential_hash` 由 adapter 自动算出（依赖 T013）

**完成态**：`pytest -k pools` 全绿；US1 可独立 demo——任何平台插件作者按 grok_adapter 模板可在 30 分钟内实现自己的 adapter（SC-001 验证基础）。

---

## Phase 4: User Story 2 — 下游可接收任意 provider 的 PoolItem 并入库 (P1)

**Story Goal**：下游 Go DTO 与上游 pydantic schema 字段级一致；同一份 fixture 双向 roundtrip 字节级匹配（FR-017）。

**Independent Test**：在下游独立验证——用 `go test ./internal/dto/...` 跑 fixture roundtrip 与 canonical hash 一致性；无需上游运行。

> ⚠️ **跨仓**：本 phase 任务在外部仓库 `~/Projects/gpt2apiup/` 执行，本仓只产出对照规范。完整的下游 import handler 改造（provider 白名单放开）属于 SPEC-002，**不**在本 spec 范围。

- [ ] T018 [P] [US2] 在下游 `~/Projects/gpt2apiup/backend/internal/dto/pool_item.go` 创建 6 个 struct（`PoolItem` / `PoolItemSource` / `LinesBatch` / `Sub2ApiBatch` / `ImportError` / `ImportResult`），字段与 JSON tag 严格对照本仓 `data-model.md` Entity 1–6
- [ ] T019 [P] [US2] 创建 `~/Projects/gpt2apiup/backend/internal/dto/canonical.go`：实现 `CanonicalHash` + `MaskCredential`，对照 data-model.md 附录 A/B
- [ ] T020 [US2] 复制 `specs/001-poolitem-contract/contracts/golden-samples.jsonl`（含 T005 重算后的真 hash）→ `~/Projects/gpt2apiup/backend/internal/dto/testdata/golden-samples.jsonl`；本步骤手工执行，记录到 T006 sync 脚本里作为下一轮自动化的输入
- [ ] T021 [US2] 创建 `~/Projects/gpt2apiup/backend/internal/dto/canonical_test.go`：与 T014 同一组 10+ 输入表驱动测试 `CanonicalHash`；预期 64 hex 与 Python 侧字节级相等
- [ ] T022 [US2] 创建 `~/Projects/gpt2apiup/backend/internal/dto/golden_samples_test.go`：用 `json.Decoder` + `dec.UseNumber()` 加载 fixture；每条 unmarshal → marshal → normalize（key 排序后 SHA-256）；与原始 line 的 normalized SHA-256 一致
- [ ] T023 [US2] 跑下游 CI：`cd ~/Projects/gpt2apiup/backend && go vet ./internal/dto/... && go test ./internal/dto/...`，全绿即 US2 done

**完成态**：双语对同一 fixture 行为完全一致，可作为契约通过的硬证据；为 SPEC-002 的 handler 改造留出明确的字段消费样板。

---

## Phase 5: User Story 3 — 维护者可演进 schema 而不破坏在跑客户端 (P2)

**Story Goal**：上下游一侧升级到 v1.1（新增可选字段）时，另一侧仍可正常解析并保留未知字段。

**Independent Test**：上游 / 下游各自跑一次"v1.0 parser 吃 v1.1 数据"和"v1.1 parser 吃 v1.0 数据"的双向测试；不需要任何业务代码。

- [x] T024 [P] [US3] 创建 `tests/pools/test_schema_evolution.py`：(a) 用 fixture 第 14 条（`schema_version="1.1"` + `mfa_seed`）→ 当前 v1.0 parser 读入不抛、`__pydantic_extra__` 含 `mfa_seed`；(b) 把 fixture 第 9 条（minimal v1.0）喂给"将来某个 v1.1 字段集"，缺失的新字段取默认 None；(c) 显式 null 与键缺失语义不同的断言（FR-002 守则）
- [ ] T025 [P] [US3] 创建 `~/Projects/gpt2apiup/backend/internal/dto/schema_evolution_test.go`：对照 T024 用 `map[string]json.RawMessage` 验证未知字段保留；显式 null 与键缺失通过 `_, ok := m["key"]` 区分 — *deferred: 跨仓任务，随 SPEC-002 PR 执行*
- [x] T026 [US3] 在 `specs/001-poolitem-contract/contracts/EVOLUTION.md` 记录"PoolItem schema 演进规则"：MAJOR vs MINOR bump 触发条件、向后兼容窗口、deprecation 流程；引用 spec.md FR-013

**完成态**：演进路径有文档背书 + 双语测试硬证据；为未来 SPEC-002 之后加新 provider 字段时提供可重复的兼容性 playbook。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: CI 集成 / 跨仓文档同步 / 最后一轮 Constitution Check

- [x] T027 [P] 在仓 root 加 `Makefile` 或 `scripts/check_poolitem_contract.sh` 一键任务：(a) 跑 T006 sync 脚本验 fixture SHA-256；(b) `pytest tests/pools/ -v`；(c) 用 `python-jsonschema` 对 fixture 文件按 `contracts/poolitem.schema.json` 全部校验；任一失败退出非 0
- [ ] T028 [P] 同步下游 API 文档：在 `~/Projects/gpt2apiup/docs/04-API规范.md` 的 `/admin/api/v1/accounts/import` 节追加 `format=sub2api` 请求样本 + 11 项错误码表（取自 spec.md FR-008）；本文件改动随 SPEC-002 的 PR 合并，不在 SPEC-001 自己的 PR 内 commit — *deferred: 跨仓任务，随 SPEC-002 PR 执行*
- [x] T029 [P] 在 `core/pools/__init__.py` 显式 export 公共 API：`PoolItem` / `PoolItemSource` / `LinesBatch` / `Sub2ApiBatch` / `ImportResult` / `ImportError` / `canonical_hash` / `mask_credential`；并在文件头 docstring 链接到 `specs/001-poolitem-contract/`
- [x] T030 跑 quickstart.md Done 自检 7 项 checklist 全部通过；把结果贴到 PR description（按 spec.md Constitution Check 表格式） — 见 `specs/001-poolitem-contract/PR-NOTES.md`（5/7 ✅，2 项跨仓 deferred）
- [x] T031 在 PR description 中填 Constitution Check：6 条原则逐项标 PASS / JUSTIFIED；不允许任何 VIOLATION — 见 `PR-NOTES.md`（6 项全部 PASS 或 JUSTIFIED，0 VIOLATION）

---

## Dependencies

```
Phase 1 (T001–T004)  Setup
        ↓
Phase 2 (T005–T008)  Foundational    ← 所有 story 阻塞依赖
        ↓ ┌──────────┬──────────┐
Phase 3 (US1, T009–T017)     ← 可与 US2 并行，但建议先做 US1（MVP）
Phase 4 (US2, T018–T023)     ← 可与 US1 并行（跨仓库不冲突）
Phase 5 (US3, T024–T026)     ← 依赖 US1 + US2 完成（双语都要有 parser 才能演练演进）
        ↓
Phase 6 (T027–T031)  Polish
```

**关键依赖**：
- T011 / T012 → 依赖 T009（canonical_hash）+ T010（schema 骨架）
- T016 → 依赖 T005（真 hash 写回 fixture）+ T007（pytest fixture）
- T020 → 依赖 T005（同一权威源）
- T021 / T022 → 依赖 T018（struct）+ T019（CanonicalHash）+ T020（fixture）
- T024 / T025 → 依赖 T010（Python schema）+ T018（Go struct）
- T027 → 依赖 T006（sync 脚本）+ T016（test_golden_samples 通过）
- T030 / T031 → 依赖 T023（下游 CI 通过）+ T027（上游一键任务通过）

---

## Parallel Execution Opportunities

**Phase 1 内部**（同时跑）：T003 + T004

**Phase 2 内部**（同时跑）：T007 + T008（T005 / T006 必须先于 T007）

**Phase 3 内部**（高并行度）：
- T009 / T010 / T013 / T014 / T015 完全独立可并行（不同文件）
- T011 / T012 必须等 T009+T010；T016 必须等 T005+T007
- T017 等 T013

**Phase 4 内部**（跨仓独立）：T018 / T019 / T020 全部可并行；T021 / T022 等前三者

**Phase 5 内部**（高并行度）：T024 + T025 完全独立；T026 与之并行

**Phase 6**：T027 / T028 / T029 可并行；T030 / T031 串行收尾

**Phase 3 与 Phase 4 之间**：完全跨仓库独立，可并行——一个人写 Python，一个人写 Go；汇合点是 Phase 5 与 Phase 6

---

## Implementation Strategy

**MVP 优先级**：
1. **最小 MVP** = Phase 1 + 2 + 3（US1）。完成后上游已能产出合法 PoolItem 与本地 pydantic 校验通过；可独立 demo 给团队看："看，这就是 SPEC-002 后续要消费的载荷形状"
2. **契约打通** = MVP + Phase 4（US2）。双语对同一 fixture 行为字节级一致——这是 SPEC-002 启动的硬前提
3. **演进保障** = + Phase 5（US3）。文档 + 测试齐备，未来任何 schema bump 都有 playbook
4. **PR 候选** = + Phase 6（Polish）。CI 接入 + 跨仓文档同步 + Constitution Check 表 → 可 merge

**建议执行节奏**（参考工时；以一人专注开发计算）：
- Day 1：Phase 1 + 2（含 T005 重算 fixture）→ 半天
- Day 1 后半 + Day 2 上午：Phase 3 全部 → 1 天
- Day 2 下午 + Day 3 上午：Phase 4 全部 → 1 天
- Day 3 下午：Phase 5 → 半天
- Day 4 上午：Phase 6 + PR → 半天
- **总计**：≈ 4 个工作日

**Done 标准**：`quickstart.md` 末尾的 7 项 checklist 全部 ✅ + PR description 中 Constitution Check 6 项无 VIOLATION。

---

## Task Counts

| Phase | 任务数 | 可并行数 |
|---|---|---|
| Phase 1 Setup | 4 | 2（T003 + T004） |
| Phase 2 Foundational | 4 | 2（T007 + T008） |
| Phase 3 US1（MVP） | 9 | 5（T009/T010/T013/T014/T015） |
| Phase 4 US2 | 6 | 3（T018/T019/T020） |
| Phase 5 US3 | 3 | 3（T024/T025/T026） |
| Phase 6 Polish | 5 | 3（T027/T028/T029） |
| **总计** | **31** | — |

**MVP scope（US1 only）**：Phase 1 + 2 + 3 = **17 tasks**，可独立交付并验证 SC-001 / SC-002。
