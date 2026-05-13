# PoolItem Schema 演进规则

**Branch**: `001-poolitem-contract` | **Constitution**: v1.0.0 Principle I

本文是 PoolItem 契约的演进 playbook。任何想动 `contracts/*.schema.json`
或 `data-model.md` 的人，先读这一份；然后再开 PR。

---

## 1. Bump 触发条件

`schema_version` 形如 `MAJOR.MINOR`（spec.md FR-011；初版固定 `1.0`）。

### MINOR bump（`1.x` → `1.(x+1)`）

允许的改动 — 双方都能在不停服的前提下吸收：

- **新增可选字段**（默认值 `None` / `null` / `omitempty`）
- **新增枚举值**到 `auth_type` / `executor` / `errors[].code`
  （消费侧旧版本对未知 enum 值降级到 `unknown` 桶；FR-008 已约束）
- **放宽既有字段约束**（e.g. 最大长度从 32 提到 64）
- **新增非必填的 schema 元字段**（e.g. 新增 `proxy_hint` 之类）
- **在 `meta` 顶层键里新增 provider 扩展**（meta 整体仍是
  `Map<string, Any>`，新键自然落入既有契约）

**MINOR PR 必经的 5 项**：

1. 在 `data-model.md` 与对应 `*.schema.json` 同步登记新字段。
2. `golden-samples.jsonl` 至少新增 1 条覆盖该字段的样本，并按
   FR-005 重算其 `credential_hash`。
3. `scripts/sync_poolitem_fixtures.sh` 跑通；上下游 fixture SHA-256 一致。
4. 上游 `pytest tests/pools/` 全绿；下游 `go test ./internal/dto/...` 全绿。
5. PR description 里登记本次 MINOR 号 + 列出新增字段。

### MAJOR bump（`1.x` → `2.0` 及以上）

只有在以下任意一项成立时触发 — 这些都是**破坏向后兼容**的动作：

- **删除字段**（或把必填字段改为可选 / 把可选字段改为必填）
- **重命名字段**（包括 JSON tag 大小写变化、snake_case ↔ camelCase）
- **收窄字段类型**（e.g. `string` → `enum`、`int64` → `int32`、放开 enum 收缩成更小集合）
- **改变 `credential_hash` 计算算法**（FR-005 的 4 步流程）
- **改变 `auth_type` 与 `credential` / `access_token` / `refresh_token`
  互斥关系**（data-model.md Entity 1 验证规则 1–3）
- **改变 `errors[].code` 枚举语义**（FR-008 11 项决策表）
- **改变 `format` 字段含义**（FR-007 lines / sub2api 的职责）
- **改变 `schema_version` 自身的格式或语义**

**MAJOR bump 是 SPEC 级动作**：

1. 必须先 amend `.specify/memory/constitution.md`（Principle I 是
   NON-NEGOTIABLE，宪法版本同步 MAJOR bump）。
2. 必须开一份新 SPEC（不能继续在 SPEC-001 里改），引用旧 SPEC + 新
   规则，并在新 SPEC 的 `Out of Scope` 段显式说明"不在旧契约范围"。
3. 上下游各自跑 **同时支持 v1 + v2 两种 parser** 的过渡版本；过渡窗口
   ≥ 2 个发布周期（见 §3）。
4. 解析方对未支持的 MAJOR 版本 MUST 返回错误码 `invalid_schema_version`
   （FR-008 已封装），**不**静默忽略，**不**强转。

---

## 2. 向后兼容窗口

| 阶段 | 上游行为 | 下游行为 | 持续时间 |
|------|----------|----------|----------|
| **N+0 发布 v2.0** | 仍发送 v1.x（默认） | 同时接受 v1.x 与 v2.0 | — |
| **N+1 切流** | 灰度切到 v2.0（按 task / executor / provider 维度） | 同上 | ≥ 2 周 |
| **N+2 全量** | 全量 v2.0；保留 v1.x 兜底配置（运行时开关） | 同上 | ≥ 2 周 |
| **N+3 弃用警告** | 全量 v2.0；删除 v1.x 兜底 | 接收 v1.x 时记 WARN 日志 + 计数指标 | ≥ 1 个完整发布周期 |
| **N+4 拒收** | — | 接收 v1.x 时返回 `invalid_schema_version` | — |

> 任何阶段都不允许跳过。上游必须比下游先**到达**每个阶段（先发后收），
> 但下游必须比上游晚**离开**每个阶段（后弃先持）。

---

## 3. Deprecation 流程（字段级）

字段废弃 ≠ 字段删除。完整流程：

```
[active] → [deprecated]（≥ 1 MINOR 期）→ [removed]（MAJOR）
```

具体动作：

1. **deprecated 入场**：在 `data-model.md` 的字段表里标 ⚠ `deprecated since 1.x`；
   `*.schema.json` 的 description 加 `(deprecated; will be removed in 2.0)`；
   `core/pools/schema.py` 与 Go struct 加注释指向迁移路径。
2. **生产数据观测**：上游统计该字段的"非 null 发送率"；下游统计"非 null
   接收率"。任何非零比例都意味着不能立刻移除。
3. **过渡期最短 4 周** 且 **观测比例归零后再 2 周**，才能进入 removed。
4. **removed 必须配 MAJOR bump**（见 §1）。

---

## 4. 不允许的"隐式"变更

下列动作即使外观上是"加字段"也**不**允许在 MINOR 内做：

- 在已有可选字段上加默认值**且**改变缺失语义（破坏 FR-002 守则 3）
- 在 `meta` 上加 `additionalProperties: false`（收窄 meta 边界 = 收窄类型）
- 在 `errors[].code` 上加 `additionalProperties: false`
  （已显式声明 `unknown` 桶机制，不允许变 closed without bump）
- 把 `executor` 从开放策略改为强制注册表（=收窄）
- 调整 `credential_hash` 的输入归一化方式（=改算法）

---

## 5. PR 模板段落（建议复制粘贴）

```markdown
### Schema bump 自检
- [ ] 本 PR 是 MINOR / MAJOR （删除其一）
- [ ] `schema_version` 已在 spec.md FR-011 段落更新
- [ ] `data-model.md` 字段表已同步
- [ ] `contracts/*.schema.json` 已同步
- [ ] `golden-samples.jsonl` 新增样本并重算 `credential_hash`
- [ ] `scripts/sync_poolitem_fixtures.sh` 跑通
- [ ] 上游 `pytest tests/pools/` 全绿
- [ ] 下游 `go test ./internal/dto/...` 全绿（跨仓 PR 已链接）
- [ ] 若 MAJOR：宪法 v* → v(*+1) MAJOR bump PR 已链接
```

---

## 6. 引用

- spec.md FR-011（schema_version 演进规则）
- spec.md FR-012（unknown field 保留）
- spec.md FR-013（MAJOR bump 触发场景）
- `.specify/memory/constitution.md` Principle I（PoolItem Contract First, NON-NEGOTIABLE）
- `data-model.md` Entity 1 验证规则 1–3（auth_type × credential 互斥）
- `contracts/README.md` §修改协议（PR 工序）
- `research.md` R5（跨仓 fixture 同步原理）
