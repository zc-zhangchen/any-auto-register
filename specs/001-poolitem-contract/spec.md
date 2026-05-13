# Feature Specification: PoolItem 中间表示协议

**Feature Branch**: `001-poolitem-contract`

**Created**: 2026-05-13

**Status**: Draft

**Input**: User description: "PoolItem 中间表示协议：上下游账号载荷统一 JSON 契约（Constitution Principle I 的实体落地）"

## Clarifications

### Session 2026-05-13

- Q: `credential_hash` 的 canonicalization 规则怎么定？ → A: `SHA-256(lower(provider) + '\n' + lower(auth_type) + '\n' + trim(credential or refresh_token))`，凭据本体大小写敏感保留，provider/auth_type 小写化，三段用 `\n` 分隔；不引入 JSON 序列化、不含 schema_version
- Q: `format=lines` 在 PoolItem 时代的语义是什么？ → A: 保留原语义——每行 = raw credential 字符串，整批共用顶层 `provider`+`auth_type`；结构化全字段推送一律走 `format=sub2api`。两种 format 不混用、不互相回退
- Q: `errors[].code` 是封闭枚举还是自由文本？ → A: 封闭枚举（首个集合 11 项见 FR-008）；新增项需 spec PR + schema_version MINOR bump；解析方遇到未知 code 一律降级为 `unknown` 桶（语义：可重试，达重试上限后人工介入）
- Q: `meta` 字段允许嵌套吗？ → A: 自由 `Map<string, Any>`，允许嵌套对象 / 数组 / 布尔 / 数字 / null；双语实现 MUST 显式约束类型边界（见 FR-002 守则）以保证 roundtrip 一致
- Q: `schema_version` 放在 PoolItem 上还是 batch 顶层？ → A: 每条 PoolItem 自带；batch 顶层不再有；同批次允许混版本；lines 模式（无 PoolItem 结构）按 `1.0` 兜底

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 平台插件作者可以用单一映射函数把注册产物变成 PoolItem (Priority: P1)

一名负责接入新厂商（比如 cursor、tavily）的工程师，需要把自己平台插件注册成功后产出的内部 Account 对象，转换成一份可以直接被下游 KleinAI 网关消费的 JSON 载荷。今天每个平台各自维护一份 `*_upload.py`，字段名漂移、出错时排查困难、新加字段要改多处。

引入 PoolItem 之后，作者只需在 `core/pools/adapters/<provider>_adapter.py` 写一个映射函数，把内部 Account 字段填到 PoolItem 的固定字段上即可；不再写任何 HTTP 调用、不再关心下游表结构、不再各自处理"OAuth 还是 Cookie"的差异。

**Why this priority**: 没有这一层契约，所有后续工作（Pusher、PoolService、错误分类）都无处落脚。这是六条原则中 Principle I 的实体落地，是其余 7 份 spec 的依赖项。

**Independent Test**: 拿一个现有平台（如 chatgpt 或 grok）已成功注册的 Account 实例，调用其 adapter 产生一个 PoolItem 对象；断言：(a) 所有必填字段非空；(b) `credential_hash` 在两次相同输入下完全一致；(c) 序列化为 JSON 后能被同一份 schema 反序列化且字段无丢失。无需启动下游服务即可独立验证。

**Acceptance Scenarios**:

1. **Given** 一个 chatgpt 注册成功的 Account（含 access_token + refresh_token + email），**When** chatgpt adapter 转换为 PoolItem，**Then** 输出的 JSON 中 `provider="gpt"`、`auth_type="oauth"`、`access_token` 和 `refresh_token` 都被填入、`credential_hash` 为非空 64-hex 字符串
2. **Given** 一个 grok 注册成功的 Account（含 SSO cookie），**When** grok adapter 转换为 PoolItem，**Then** 输出 `provider="grok"`、`auth_type="cookie"`、`credential` 等于 SSO token、`expires_at` 不晚于注册时间 +72 小时
3. **Given** 两次调用 adapter 输入完全相同的 Account，**When** 比较两次 PoolItem 的 `credential_hash`，**Then** 两个哈希字节级相等
4. **Given** 一份在 `meta` 字段里带了 adapter 不认识的扩展键的 PoolItem JSON，**When** 解析方读取，**Then** 解析成功且未知键以原样保留（forward-compatible）

---

### User Story 2 - 下游网关运维可以接收任意 provider 的 PoolItem 并入库 (Priority: P1)

KleinAI 管理后台的运维通过现有的 `POST /admin/api/v1/accounts/import` 端点接收上游推送。当前下游只识别 `provider=gpt|grok` 两种值，其他都会被 400 拒绝。本协议要求该端点接受**所有已在下游 provider 注册表中登记的 provider**（gpt、grok、kiro、cursor、openblocklabs、tavily…），并按统一规则解码 PoolItem、加密入库、返回 imported/skipped/failed 统计。

注意：本 spec **只定义契约形状**，不实施下游 provider 扩容的代码改造——那是 SPEC-002 的工作。本 spec 的产出是：让 SPEC-002 在改 Go 代码时有一份可以照抄的请求/响应 JSON 范例。

**Why this priority**: Principle II "Single Downstream Channel"要求所有交付都走这一根管子；契约不定下来，SPEC-002 改 Go 代码时仍要猜字段名。P1 与 Story 1 同级，因为没有这一端的输入合同，Story 1 的输出无处可去。

**Independent Test**: 用一份手写的 PoolItem JSON（任意 provider），通过 curl 或 Postman 投递到一个 mock 下游 endpoint；断言：(a) Content-Type、Authorization 头符合契约；(b) 请求体能被同一份 schema 解析为等价对象；(c) 响应体形状符合契约（含 imported/skipped/failed 计数 + 可选错误列表）。

**Acceptance Scenarios**:

1. **Given** 一份合法的 PoolItem 批次（5 条 grok），**When** 通过 `format=sub2api` 单次 POST 提交，**Then** 响应 `imported=5, skipped=0, failed=0` 且 HTTP 200
2. **Given** 同一份 PoolItem 批次被推送第二次，**When** 提交，**Then** 响应 `imported=0, skipped=5, failed=0` 且 HTTP 200（幂等，不是错误）
3. **Given** PoolItem 中 `provider` 是下游尚未登记的 provider，**When** 提交，**Then** 响应 HTTP 400 + 错误码 `unknown_provider` + 列出已支持的 provider 列表
4. **Given** PoolItem 缺少必填字段 `credential`，**When** 提交，**Then** 响应 HTTP 400 + 错误码 `missing_required_field` + 字段路径 `credential`

---

### User Story 3 - 维护者可以新增字段而不破坏在跑的上下游 (Priority: P2)

一年后某个新平台需要在 PoolItem 里携带"双因子验证种子"这个新字段。维护者希望在不停服、不强制升级所有上游客户端、不破坏所有已有 adapter 的前提下，把新字段加进契约。

**Why this priority**: 没有这条，前述两条会因字段演进而频繁返工。属于 P2 是因为它只在第二次/第三次扩字段时才显式起作用。

**Independent Test**: 写两个版本的 PoolItem schema（v1.0 和 v1.1，后者多一个可选字段）；用 v1.0 序列化的 JSON 喂给 v1.1 解析器，断言成功且新字段为默认值；用 v1.1 序列化的 JSON 喂给 v1.0 解析器，断言成功且未知字段被忽略。

**Acceptance Scenarios**:

1. **Given** schema_version="1.0" 的 PoolItem JSON，**When** 被 schema_version="1.1" 的 parser 解析，**Then** 成功，缺失的新字段取定义中的默认值
2. **Given** schema_version="1.1" 的 PoolItem JSON 含 v1.0 不认识的可选字段 `mfa_seed`，**When** 被 v1.0 parser 解析，**Then** 成功且未知键保留在 `meta` 或被静默忽略
3. **Given** 一次 MAJOR 字段重命名（违反向后兼容），**When** schema_version 仍为 1.x，**Then** spec 流程禁止合并（由宪法治理章节兜底，本 spec 仅声明该不变式）

---

### Edge Cases

- **凭据轮转 vs 全新凭据**：同一邮箱触发第二次注册得到新的 refresh_token 时，新 PoolItem 的 `credential_hash` 一定不同于旧的（因为 hash 输入含凭据字节）。这天然导致下游会"新增一条"而非"更新一条"。本 spec 把此行为定义为**正确行为**：旧条目通过下游探测/过期机制自然淘汰，避免覆盖式更新带来的审计漏洞。
- **批次内部分失败**：导入 100 条，其中 3 条凭据格式错误。响应必须返回 `imported=97, skipped=0, failed=3` 且 `errors[]` 列出 3 条的下标和原因，**不能整批 rollback**。
- **极大 batch**：批次超过 500 条（plus_gopay / KleinAI 经验值）时，本协议规定上游 Pusher MUST 自行分片；下游若收到超长批次，MUST 返回 HTTP 413 + 错误码 `batch_too_large`，不静默截断。
- **空 `credential` 但 OAuth 双 token 都齐全**：当 `auth_type=oauth` 且 `access_token` 与 `refresh_token` 至少有其一非空时，`credential` 字段允许为空字符串。
- **`expires_at` 缺失**：cookie 类 provider 没法获得 TTL 时，`expires_at` 留空；下游可调度自己的探测任务推断实际过期。
- **上游脏字符**：来自 yes-captcha / OCR 流程的字段可能带前后空白或控制字符，adapter MUST 在生成 PoolItem 前 trim 并删除 `\x00-\x1f`，避免下游 SQL 写入失败。

## Requirements *(mandatory)*

### Functional Requirements

**Schema 字段（契约本体）**

- **FR-001**: PoolItem MUST 包含必填字段：`schema_version`、`provider`、`auth_type`、`credential`（或 OAuth 双 token 至少一项）、`credential_hash`、`source`
- **FR-002**: PoolItem MUST 包含可选字段：`access_token`、`refresh_token`、`email`、`weight`、`proxy_hint`、`expires_at`、`region`、`meta`。`meta` 是自由 `Map<string, Any>` 用于承载 provider 扩展，双语实现 MUST 遵守下列类型守则以保证字节级 roundtrip：
  - **允许值类型**：`string` / `int64` / `float64` / `bool` / `null` / `list` / 嵌套 `Map<string, Any>`（深度 ≤ 4）
  - **整数处理**：Go 解析方 MUST 使用 `json.Number` 或 `*int64` 字段以避免 `int → float64` 损失（值 > 2^53 时尤其关键）；pydantic 侧 MUST 用 `int` 注解（不要 `int | float` 的联合）
  - **null 语义**：键存在且值为 `null` 与"键缺失"MUST 视为**不同**含义（前者表示显式清空、后者表示未设置）
  - **键名约束**：只允许 ASCII、`[a-z0-9_.-]`；不允许空格、Unicode、`$`、`@`
  - **数组同构性**：同一数组内所有元素 MUST 类型相同（不允许 `[1, "a", true]` 这种异构）
  - **黄金样本（FR-018）覆盖**：至少包含一条带 `int64 > 2^53`、一条带嵌套对象、一条带数组、一条带显式 `null` 的样例，强制双语 CI 验证 roundtrip
  - **平台扩展示例**：kiro 的 `client_id`、chatgpt 的 `sentinel_token`、grok 的 `region_hint` 都放在 `meta` 顶层键
- **FR-003**: `provider` 字段的合法值 MUST 来自一个枚举集合，该集合由"已在下游 model + factory 注册"的 provider 决定（与宪法 Principle IV 一致）
- **FR-004**: `auth_type` 字段 MUST 在 `cookie | oauth | apikey` 三选一
- **FR-005**: `credential_hash` MUST 通过下列确定性算法产生，作为下游幂等键：
  1. `p = lower(provider)`，`a = lower(auth_type)`（仅这两段大小写归一化）
  2. `c = trim(credential)`；若 `credential` 为空且 `auth_type=oauth`，则 `c = trim(refresh_token)`
  3. `payload = p + '\n' + a + '\n' + c`（UTF-8 字节序列，两个分隔符均为单字符 `0x0A`）
  4. `credential_hash = lowercase(hex(SHA-256(payload)))`，长度 MUST 恒为 64
  5. 不引入 JSON 序列化、不掺入 `schema_version`，避免库版本/字段顺序差异破坏双语一致性

**协议交换（请求 / 响应 / 编码）**

- **FR-006**: 上游 Pusher MUST 通过 HTTPS 投递；HTTP 头 MUST 包含 `Authorization: Bearer <admin-jwt>` 与 `Content-Type: application/json`
- **FR-007**: 请求体 MUST 支持两种 format，二者职责不重叠、不互相回退：
  - `format=lines`（轻量通道，向后兼容）：`{ "format":"lines", "provider":"...", "auth_type":"...", "text":"tok1\ntok2\n..." }`；整批共用顶层 `provider` + `auth_type`，`text` 是 `\n` 分隔的 raw credential 字符串；用于历史 `register-to-pool` 脚本与单 provider 快速粘贴
  - `format=sub2api`（结构化通道）：`{ "format":"sub2api", "accounts": PoolItem[] }`；每条 PoolItem 自携 provider / auth_type / meta / source 等完整字段，支持同一批次混用 provider
  - 解析方 MUST 根据 `format` 字段分支，不允许"先试 JSON 再 fallback raw"等混合解析
- **FR-008**: 响应体 MUST 包含 `imported`、`skipped`、`failed` 三个非负整数计数；当 `failed > 0` 时 MUST 附带 `errors[]`，每项含 `index`、`code`、`message`。`code` 是封闭枚举，本 spec 锁定**首个 11 项集合**：

  | Code | 触发场景 | Pusher 决策语义 |
  |------|----------|-----------------|
  | `unknown_provider` | provider 未在下游 model + factory 注册 | `mark_dead`（不可重试；需 SPEC-002 类工作扩注册） |
  | `missing_required_field` | 必填字段缺失 | `mark_dead`（adapter bug） |
  | `invalid_credential_format` | credential / token 格式校验失败 | `mark_dead`（adapter bug） |
  | `invalid_schema_version` | `schema_version` 不在下游可接受范围 | `mark_dead`（上下游版本断层，走 spec 演进） |
  | `batch_too_large` | 批次 > 500 | `retry_now`（上游切片后再投） |
  | `expired_credential` | 凭据已过 `expires_at` | `mark_dead`（重新注册） |
  | `rate_limited` | 下游入库限流 | `retry_later`（指数退避） |
  | `downstream_unavailable` | 下游 5xx / 网络抖动 | `retry_later` |
  | `internal_error` | 下游未分类异常 | `retry_later`，达上限转 `human_review` |
  | `forbidden` | Admin JWT 失效 / 鉴权失败 | `human_review`（JWT 刷新由运维介入） |
  | `unknown` | 上面 10 项之外的未来值（兼容缓冲） | `retry_later`，达上限转 `human_review` |

  - 演进规则：新增 code 需走 spec PR + `schema_version` MINOR bump；解析方遇到未在已知集合内的 code MUST 降级为 `unknown` 桶处理而非崩溃
- **FR-009**: 同一 `credential_hash` 的重复推送 MUST 计入 `skipped`，HTTP 状态 MUST 仍为 2xx
- **FR-010**: 单次请求批次大小 MUST 不超过 500 条；超出时下游 MUST 返回 HTTP 413 + `batch_too_large`

**兼容与演进**

- **FR-011**: `schema_version` 字段挂在**每条 PoolItem** 上（非 batch 顶层），首版固定 `"1.0"`；后续添加可选字段 MUST 保持 `schema_version` 仍为 `1.x`：
  - 同一批次内 PoolItem 允许混版本（上游灰度发布友好），下游按条解析、按条决策
  - `format=lines` 模式不携带 PoolItem 结构，整批按隐式 `schema_version="1.0"` 解析；本规则不会因将来 schema 演进而改变（lines 通道永久锁定 1.0）
  - PoolItem 缺省 `schema_version` 时下游 MUST 按 `"1.0"` 兜底（向后兼容 `register-to-pool` 等历史 caller）
  - 解析方对未来 MAJOR 版本（如 `2.x`）的条目 MUST 返回 `invalid_schema_version` 错误码并附 `index`，不静默忽略
- **FR-012**: 解析方 MUST 忽略未在当前 schema 版本中声明的额外字段，并 MUST 不报错
- **FR-013**: 任何删除字段、改变字段语义、收窄字段类型的变更 MUST 触发 `schema_version` 的 MAJOR bump（升至 `2.0`）

**安全与审计**

- **FR-014**: 凭据字段（`credential`、`access_token`、`refresh_token`）在传输中 MUST 仅依赖 TLS 保护，不得在 JSON 层做二次加密或编码混淆（避免破坏可读性 + 增加密钥协调成本）
- **FR-015**: 任何记录 PoolItem 的日志（上游 push_logs、下游审计）MUST 对凭据字段进行掩码，保留前 4 + 后 4 字符，中间以 `…` 替代
- **FR-016**: `source` 字段 MUST 携带 `task_id`、`registered_at`（ISO 8601 UTC）、`executor`（`protocol|headless|headed`），用于故障追溯

**多语言一致性**

- **FR-017**: 契约 MUST 同时落地为 Python pydantic 模型（上游 `core/pools/schema.py`）和 Go struct（下游 `internal/dto/pool_item.go`），字段名、JSON tag、可选性 MUST 字节级一致
- **FR-018**: 两侧实现 MUST 共享一组黄金测试样本（jsonl 文件），双语都基于它做序列化 / 反序列化往返测试

### Key Entities

- **PoolItem**：一条注册产物的标准化载荷。承载身份（provider + credential_hash）、凭据（credential / oauth tokens）、上下文（email、proxy_hint、expires_at）、扩展（meta）、溯源（source）。是上下游唯一的通用语。
- **PoolItemBatch**：PoolItem 的有序集合 + 投递元数据（`format`、可选 `proxy_id`、可选 `default_weight`）。下游通过它进行批量入库的事务边界。
- **ImportResult**：下游对一次批次投递的应答。含三计数 + 可选错误列表。是 Pusher 决定"重试 / 标记完成 / 报告失败"的唯一信号源。
- **SchemaVersion**：契约自身的版本号，独立于上下游应用版本。决定字段集合与可选性的快照。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：在引入 PoolItem 之后，新增一个第三方平台从 0 接入下游的工作量从"修改 5 个文件平均 3 小时"降低到"新建一个 adapter 文件 30 分钟内"（用 cursor 或 openblocklabs 的接入工时实测验证）
- **SC-002**：现有 6 个平台（chatgpt、grok、kiro、cursor、openblocklabs、tavily）100% 可表达为 PoolItem，且无业务关键字段（如 trial_end_time、region）在序列化过程中丢失
- **SC-003**：同一批 PoolItem 重复推送，第二次的 `skipped` 比例为 100%，`failed` 为 0
- **SC-004**：上下游双语黄金样本（不少于 20 条覆盖 3 种 auth_type）双向往返测试 100% 通过；任意一侧字段名 / 大小写漂移会让 CI 立刻挂红
- **SC-005**：在 schema 从 v1.0 演进到 v1.1（新增一个可选字段）的演练中，未升级的上游与未升级的下游可继续通信，无数据丢失、无错误响应
- **SC-006**：100 条批次端到端（adapter 产出 → Pusher 投递 → 下游入库 → admin GET /accounts 查到）耗时 P95 ≤ 2 秒（本地内网；不含 TLS 握手）

## Assumptions

- 上游与下游均通过 HTTPS 通信，TLS 终止由部署侧（Caddy / Nginx）负责；本契约不规范底层 TLS 版本
- 下游 `/admin/api/v1/accounts/import` 已存在并接受 Admin JWT 鉴权；本 spec 不重建该 endpoint，只扩字段
- 下游 AES-256-GCM 加密入库由 `KLEIN_AES_KEY` 提供（宪法 Principle III）；本 spec 只规定**传输层不二次加密**
- `credential_hash` 仅用作幂等键，不用作安全凭据；攻击者获得哈希也无法反推凭据
- 上游使用 Python 3.11+；下游使用 Go 1.24+；pydantic v2 与 Go struct 在 JSON 字段名（snake_case）上完全一致
- `expires_at` 为 ISO 8601 UTC 字符串，时区 MUST 显式（含 `Z` 或 `+00:00`），不依赖解析方本地时区
- 任何下游 provider 路由（gpt 走 OpenAI、grok 走 x.ai 等）由下游 factory 决定，PoolItem **不**携带路由提示

## Downstream Impact

本节按宪法治理要求显式声明对下游的触动：

- **下游 provider 注册表**：本 spec 只**声明**契约接受任意已注册 provider，但**不实施**新 provider 的注册（那是 SPEC-002 的范围）。两份 spec 必须按顺序 merge：001 → 002 → 003。
- **下游迁移**：本 spec 不要求下游数据库迁移。若 SPEC-002 决定改 enum，则在 SPEC-002 的 migration 中处理。
- **下游 API 文档**：本 spec 合并后，`gpt2apiup/docs/04-API规范.md` MUST 同步更新 `/admin/api/v1/accounts/import` 的请求 / 响应 JSON 示例。
- **下游兼容性**：现有 `format=lines` + 单字符串 token 的轻量推送方式 MUST 仍然有效；本 spec 是叠加新契约（`format=sub2api` + PoolItem 数组），不是替换。

## Out of Scope

为避免范围蔓延，下列工作明确**不**属于本 spec：

- 上游 Pusher 的实现（SPEC-004）
- 上游 PoolService、PoolAdapter 的实现（SPEC-003）
- 下游 provider 扩容 / factory 工厂实现 / 数据库迁移（SPEC-002）
- 资产池（mail / proxy / phone）改造（SPEC-005）
- 错误分类、重试调度、WebSocket 事件（SPEC-006）
- 前端动态表单（SPEC-007）
- 端到端 e2e 测试套件（SPEC-008）—— 本 spec 只产出 schema 与黄金样本
