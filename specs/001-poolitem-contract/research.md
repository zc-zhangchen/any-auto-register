# Phase 0 — Research: PoolItem 中间表示协议

**Branch**: `001-poolitem-contract` | **Date**: 2026-05-13

本研究文档解决 plan.md 中 Technical Context 与 spec.md 中 Deferred 项的所有 "NEEDS CLARIFICATION"。每条按"Decision / Rationale / Alternatives considered"三段式记录。

---

## R1 — Admin JWT 的 TTL 与刷新流程

**Decision**：Admin JWT 由下游 `/admin/api/v1/auth/login` 颁发，**TTL 固定 8 小时**；上游 Pusher MUST 实现"懒刷新"：每次推送前检查本地缓存 token 的 `exp` claim，若距过期 < 10 分钟则在推送前重新登录获取新 token。Token 缓存仅在内存（不落盘、不入 git）。批次中途收到 HTTP 401 / `forbidden` 一律视为需要刷新，刷新成功后**整批次**重投一次（不是单条），失败则进入 `human_review`。

**Rationale**：
- 8 小时是 KleinAI 现有运维实践（gpt2apiup `backend/internal/middleware/jwtpayload`）的默认值，无需改动下游
- 懒刷新比定时刷新简单（无 goroutine / asyncio task），适合上游单进程批量场景
- 重投整批次而非单条：本 spec 的 `credential_hash` 幂等已经保证已成功的 PoolItem 被去重，重投是无害的；按单条重投会让代码复杂度爆炸
- 不持久化 token：减少凭据外泄面，符合宪法 Principle III

**Alternatives considered**：
- 长寿 token（如 7 天）：扩大泄露面、与 KleinAI 现网不一致——拒绝
- 定时刷新（每 7h59m）：增加复杂度且边界条件多——拒绝
- mutual TLS 替代 JWT：架构变更幅度过大，留给未来 spec——拒绝

---

## R2 — pydantic v2 处理 `Dict[str, Any]` + int64 > 2^53 + 显式 null

**Decision**：
- pydantic 模型字段定义为 `meta: dict[str, Any] | None = None`，配合 `model_config = ConfigDict(extra='allow')`
- 整数承载用 `int` 标注（pydantic v2 默认 `int` 不会被压成 float）
- JSON 序列化时使用 `model_dump_json(exclude_none=False, by_alias=True)`；`exclude_none=False` 是关键——保留显式 `null` 以与 Go 侧"键缺失 vs 键存在为 null"的区分对齐（FR-002 守则）
- 反序列化对未知键：因 `extra='allow'`，未知键进入 `model.__pydantic_extra__`，roundtrip 时保留

**Rationale**：
- pydantic v2 在 Rust core 中对 int 不做 float coerce（与 v1 行为差异；查阅了 pydantic 官方迁移文档）
- `exclude_none=False` 是 FR-002 "显式 null 与键缺失不同"的实现
- `extra='allow'` 满足 FR-012 "解析方 MUST 忽略未知字段"

**Alternatives considered**：
- 用 `JsonValue` 自定义类型替代 `Any`：额外抽象，团队不熟，且 IDE 友好度不增——拒绝
- 用 `pydantic.TypeAdapter[dict]` 单独校验 `meta`：与字段嵌入冲突——拒绝
- 用 `orjson` 替代 stdlib `json`：性能确实更好但引入新依赖，未达瓶颈不引入——拒绝

---

## R3 — Go 端整数精度与显式 null 处理

**Decision**：
- Go struct 中 `Meta` 字段类型为 `map[string]json.RawMessage`，**延迟解码**到具体值（而非直接 `map[string]any`）
- 解码大数：用 `json.Decoder` + `dec.UseNumber()`，使 `json.Number` 替代 `float64` 承载整数，保留 int64 > 2^53 精度
- 显式 null：`map[string]json.RawMessage` 中 `RawMessage == []byte("null")` 与键缺失天然可区分，符合 FR-002
- 序列化大整数：用 `strconv.FormatInt(..., 10)` 后再 `json.RawMessage(...)`，避免 marshaller 走 float64

**Rationale**：
- `json.RawMessage` 是 Go stdlib 解决"我现在不想 decode，但要保真"的官方惯用法
- `UseNumber` 是 stdlib 文档明列的"避免大整数精度丢失"建议
- 这两个机制配合 pydantic v2 默认行为，可以让双语 roundtrip 在 `meta` 上字节级一致（除空白格式外）

**Alternatives considered**：
- `map[string]any` + `dec.UseNumber()`：仍能保留精度，但 `json.Number` 在 `any` 里嵌套到第二层就需要每层断言——拒绝
- 引入 `github.com/buger/jsonparser` 等第三方库：增加供应链面，stdlib 已足够——拒绝
- 用 `interface{ json.Marshaler }` 强类型 meta：违反 FR-002"自由 Map"决策——拒绝

---

## R4 — 契约权威源格式选型：JSON Schema 2020-12 vs OpenAPI 3.1

**Decision**：使用 **JSON Schema draft 2020-12** 单独编写 3 个 schema 文件（`poolitem.schema.json` / `poolitem-batch.schema.json` / `import-result.schema.json`），**不**生成 OpenAPI 文档（OpenAPI 由下游 gpt2apiup 用 swag 注释自维护，本 spec 不重复造轮）。

**Rationale**：
- JSON Schema 是 OpenAPI 3.1 的真子集；选 JSON Schema 不会让未来引入 OpenAPI 增加成本
- 单文件可被 `ajv`（Node）、`jsonschema`（Python）、`gojsonschema`（Go）三个生态直接校验，CI 工具链选择多
- OpenAPI 还需要 endpoint 描述（path / method / parameters），但本 spec 是数据契约不是 API 契约——避免歧义
- 已有的 `gpt2apiup/docs/04-API规范.md` 是人写的 markdown，PoolItem 落地后会同步更新（spec.md 的 Downstream Impact 已声明）

**Alternatives considered**：
- 直接写 OpenAPI 3.1：耦合 endpoint 描述，与"契约 vs API"分层混淆——拒绝
- 用 Protobuf + gRPC-Gateway：架构变更过大，且 KleinAI 现网是纯 HTTP JSON——拒绝
- 仅靠 pydantic / Go struct 互相对照：缺少独立权威源，PR review 容易漂——拒绝

---

## R5 — 跨仓库 fixture（黄金样本）同步策略

**Decision**：
- **首版（SPEC-001 完成时）**：契约权威源在 `specs/001-poolitem-contract/contracts/golden-samples.jsonl`；两个仓库在自己的 `testdata/` / `fixtures/` 下各自存一份**手工同步**的拷贝；CI 启动时计算两份的 SHA-256 与权威源比较，不一致直接失败
- **未来（SPEC-008 引入跨仓 CI 时）**：改用 git submodule 或 GitHub Action 把权威源 pull 到两个仓库 `testdata/` 下；本 spec 暂不引入 submodule（避免拖慢首次落地）

**Rationale**：
- 首版手工同步可控 + 透明：开发者改契约时一定要主动 `cp` 到两仓库，强制走两个 PR，避免"上游改了下游忘"
- SHA-256 校验是最便宜的"飘移检测"，单语言 CI 内 5 行 shell 实现
- submodule 在多人协作时是个常见绊脚石（git submodule update 漏跑），SPEC-008 引入时再加教学文档

**Alternatives considered**：
- npm package / Python wheel 发布契约：引入打包发布流程，过度工程化——拒绝
- 跨仓 git submodule：未来 SPEC-008 可选项；首版不引入——延后
- 不做 fixture 校验，仅靠人工 review：违反宪法 Principle VI 的"代码决定 done"——拒绝

---

## R6 — 凭据掩码算法（FR-015 短 token 边界）

**Decision**：
- 凭据掩码使用 `mask(s)`：若 `len(s) >= 12`，取 `s[:4] + '…' + s[-4:]`；若 `4 <= len(s) < 12`，取 `s[:1] + '…' + s[-1:]`；若 `len(s) < 4`，整体替换为 `'…'`（不暴露任何字符）
- 双语 reference 实现写入 `data-model.md` 附录

**Rationale**：
- 原 spec 的 "前 4 + 后 4 + …" 规则在短 token 上会泄露全部字符；本规则为短 token 提供退化路径
- `'…'`（U+2026）单字符易识别，便于运维肉眼区分"已掩码"与"原文"
- 双语 reference 实现可作为黄金样本的一部分校验

**Alternatives considered**：
- 固定显示 `'****'`：无法肉眼区分不同凭据用于追溯——拒绝
- 显示 `len + hash 前 8 字符`：更安全但运维不友好——拒绝
- 不做掩码降级，短 token 直接报错：太严苛，会让单元测试无法用短假值——拒绝

---

## 研究结论汇总

| ID | 主题 | Decision 一句话 |
|---|---|---|
| R1 | Admin JWT 生命周期 | 8h TTL + 懒刷新 + 401 整批次重投 |
| R2 | pydantic v2 meta 处理 | `dict[str, Any]` + `extra='allow'` + `exclude_none=False` |
| R3 | Go meta 处理 | `map[string]json.RawMessage` + `UseNumber()` |
| R4 | 契约格式 | JSON Schema 2020-12，不生 OpenAPI |
| R5 | Fixture 同步 | 首版手工 + SHA-256 校验；submodule 留给 SPEC-008 |
| R6 | 凭据掩码 | 分三段长度策略，保证短 token 不泄漏 |

所有 NEEDS CLARIFICATION 已解决。进入 Phase 1（data-model.md + contracts/ + quickstart.md）。
