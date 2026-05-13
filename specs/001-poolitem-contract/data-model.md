# Phase 1 — Data Model: PoolItem 中间表示协议

**Branch**: `001-poolitem-contract` | **Date**: 2026-05-13

本文件以 spec.md 的 Key Entities 节为基础，给出**实体级别**的字段、类型、约束、关系；并双语对照（Python pydantic v2 / Go struct）。JSON Schema 在 `contracts/*.schema.json` 中是机器可读权威源，本文件是人类可读说明书。

---

## 实体清单与关系图

```
ImportRequest ──contains──► PoolItemBatch
                              │
                              ├─ lines variant: text + provider + auth_type
                              └─ sub2api variant: accounts[]: PoolItem[]
                                                              │
                                                              ├─ source: PoolItemSource
                                                              └─ meta: Map<string, Any>

ImportResponse ──contains──► ImportResult
                              │
                              └─ errors[]: ImportError[]
```

---

## Entity 1 — `PoolItem`

承载一条注册产物的标准化载荷。

### 字段表

| 字段 | 类型 | 必填？ | 约束 |
|------|------|--------|------|
| `schema_version` | `string` | 缺省 `"1.0"` | 形如 `MAJOR.MINOR`；初版固定 `"1.0"`；解析方对 `>=2.x` MUST 返回 `invalid_schema_version` |
| `provider` | `string` (enum) | ✅ | 仅取下游 model + factory 已注册的 provider 名；首批 `"gpt"` 或 `"grok"`（SPEC-002 扩 kiro/cursor/openblocklabs/tavily） |
| `auth_type` | `string` (enum) | ✅ | `"cookie" \| "oauth" \| "apikey"` |
| `credential` | `string` | ✅* | `*` 当 `auth_type=oauth` 且 `access_token` 或 `refresh_token` 至少有其一非空时，可为空字符串 |
| `credential_hash` | `string` | ✅ | 64 字符小写 hex（SHA-256）；按 spec.md FR-005 算法产生 |
| `access_token` | `string` | ❌ | 仅 `auth_type=oauth` 有意义 |
| `refresh_token` | `string` | ❌ | 仅 `auth_type=oauth` 有意义 |
| `email` | `string` | ❌ | 邮箱格式（不强校验，因部分 provider 不暴露） |
| `weight` | `int` | ❌ | 取值 `[1, 10000]`；缺省时下游用 `100`（与 KleinAI 现行默认对齐） |
| `proxy_hint` | `string` | ❌ | 形如 `scheme://user:pass@host:port`；下游决定是否绑定，**非**路由指令 |
| `expires_at` | `string` | ❌ | ISO 8601 UTC（含 `Z` 或 `+00:00`） |
| `region` | `string` | ❌ | provider 自定义区域码，如 `"us-east-1"` |
| `meta` | `object` | ❌ | 自由 `Map<string, Any>`，深度 ≤ 4，遵循 spec.md FR-002 6 条守则 |
| `source` | `PoolItemSource` | ✅ | 见 Entity 4 |

### 验证规则（cross-field）

1. 若 `auth_type=cookie`，则 `credential` MUST 非空字符串
2. 若 `auth_type=oauth`，则 `credential` / `access_token` / `refresh_token` 至少一个非空
3. 若 `auth_type=apikey`，则 `credential` MUST 非空字符串
4. `credential_hash` MUST 与"用 spec.md FR-005 算法重算"的结果相等
5. `meta` 嵌套深度 ≤ 4；数组同构性见 FR-002

### Python（pydantic v2）

```python
# 仅展示形状，正式实现见 /speckit-implement
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal

class PoolItem(BaseModel):
    model_config = ConfigDict(extra='allow', populate_by_name=True)

    schema_version: str = "1.0"
    provider: str                           # 运行时验证：下游已注册集合
    auth_type: Literal["cookie", "oauth", "apikey"]
    credential: str = ""
    credential_hash: str = Field(min_length=64, max_length=64)
    access_token: str | None = None
    refresh_token: str | None = None
    email: str | None = None
    weight: int | None = Field(default=None, ge=1, le=10000)
    proxy_hint: str | None = None
    expires_at: str | None = None           # ISO 8601 字符串，不解析为 datetime
    region: str | None = None
    meta: dict[str, Any] | None = None
    source: "PoolItemSource"

    @model_validator(mode="after")
    def _check_credential_hash(self) -> "PoolItem":
        # 见 quickstart.md 中的 canonical_hash() 参考实现
        ...
```

### Go（struct）

```go
// 仅展示形状，正式实现见 /speckit-implement
type PoolItem struct {
    SchemaVersion  string                     `json:"schema_version"`
    Provider       string                     `json:"provider"`
    AuthType       string                     `json:"auth_type"`
    Credential     string                     `json:"credential"`
    CredentialHash string                     `json:"credential_hash"`
    AccessToken    *string                    `json:"access_token,omitempty"`
    RefreshToken   *string                    `json:"refresh_token,omitempty"`
    Email          *string                    `json:"email,omitempty"`
    Weight         *int                       `json:"weight,omitempty"`
    ProxyHint      *string                    `json:"proxy_hint,omitempty"`
    ExpiresAt      *string                    `json:"expires_at,omitempty"`
    Region         *string                    `json:"region,omitempty"`
    Meta           map[string]json.RawMessage `json:"meta,omitempty"`
    Source         PoolItemSource             `json:"source"`
}
```

### 双语对齐要点

- 所有 JSON 字段名 snake_case，**不允许**任一侧使用 camelCase
- 可选字段在 Go 侧用 `*T`（区分缺失 vs 显式零值）；在 Python 侧用 `T | None`
- `weight` 在 Python 侧 `int | None`，Go 侧 `*int`，序列化 `omitempty` 让"未设置"与"显式 0"区分（实际 weight=0 违规会被 validator 拦截）

---

## Entity 2 — `PoolItemBatch (lines variant)`

兼容 `register-to-pool` 等历史 caller 的轻量批次形态。

### 字段表

| 字段 | 类型 | 必填？ | 约束 |
|------|------|--------|------|
| `format` | `string` (const) | ✅ | 固定字面量 `"lines"` |
| `provider` | `string` (enum) | ✅ | 同 PoolItem.provider |
| `auth_type` | `string` (enum) | ✅ | 同 PoolItem.auth_type |
| `text` | `string` | ✅ | `\n` 分隔的 raw credential 字符串；空行 / `#` 注释 MUST 由下游忽略 |
| `proxy_id` | `int` | ❌ | 下游已有的 proxy 表外键 |
| `weight` | `int` | ❌ | 整批默认 weight；同 PoolItem.weight 取值范围 |

### 验证规则

1. `text` MUST 至少含一行非空、非注释内容
2. 拆分后行数 MUST ≤ 500（同 FR-010）
3. **隐式** `schema_version = "1.0"`（永久锁定，见 FR-011）

---

## Entity 3 — `PoolItemBatch (sub2api variant)`

结构化批次，承载 PoolItem 数组。

### 字段表

| 字段 | 类型 | 必填？ | 约束 |
|------|------|--------|------|
| `format` | `string` (const) | ✅ | 固定字面量 `"sub2api"` |
| `accounts` | `PoolItem[]` | ✅ | 长度 `[1, 500]` |
| `proxy_id` | `int` | ❌ | 整批 fallback 代理；单条 `proxy_hint` 优先 |
| `default_weight` | `int` | ❌ | 缺省 `100`；单条 `weight` 优先 |

### 验证规则

1. `accounts.length >= 1`；空批次 MUST 返回 HTTP 400 + `missing_required_field`
2. `accounts.length <= 500`；超出返回 HTTP 413 + `batch_too_large`
3. 批次内允许混 `schema_version`（FR-011）

---

## Entity 4 — `PoolItemSource`

注册溯源信息。

### 字段表

| 字段 | 类型 | 必填？ | 约束 |
|------|------|--------|------|
| `task_id` | `string` | ✅ | UUID v4 或自增 ID 字符串，长度 ≤ 64 |
| `registered_at` | `string` | ✅ | ISO 8601 UTC（含 `Z` 或 `+00:00`） |
| `executor` | `string` (enum) | ✅ | `"protocol" \| "headless" \| "headed"` |
| `registrar_version` | `string` | ❌ | any-auto-register 语义版本，便于排错 |

---

## Entity 5 — `ImportResult`（响应体本体）

下游对 `POST /admin/api/v1/accounts/import` 的应答。

### 字段表

| 字段 | 类型 | 必填？ | 约束 |
|------|------|--------|------|
| `imported` | `int` | ✅ | `>= 0`；本次新入库条数 |
| `skipped` | `int` | ✅ | `>= 0`；命中 `credential_hash` 重复而跳过 |
| `failed` | `int` | ✅ | `>= 0`；解析 / 校验失败条数 |
| `errors` | `ImportError[]` | ❌ | 当 `failed > 0` 时 MUST 出现 |
| `request_id` | `string` | ❌ | 下游用于审计与 Pusher 关联日志 |

### 不变式

- `imported + skipped + failed == 提交的 PoolItem 数`（含 lines 模式展开后的行数）
- 当 `failed == 0`，`errors` 字段 MUST 缺失或为 `[]`

---

## Entity 6 — `ImportError`

`errors[]` 内的单项。

### 字段表

| 字段 | 类型 | 必填？ | 约束 |
|------|------|--------|------|
| `index` | `int` | ✅ | 在原请求 `accounts[]` 或 `text` 拆分后的 0-based 下标 |
| `code` | `string` (enum) | ✅ | 见 spec.md FR-008 的 11 项封闭枚举 |
| `message` | `string` | ✅ | 人类可读说明，**不得**包含原始凭据字节 |
| `field` | `string` | ❌ | 当 `code=missing_required_field` 时给出字段路径，如 `"credential"` 或 `"meta.client_id"` |

---

## 状态转移（生命周期）

PoolItem 本身**无状态**，是不可变载荷。状态属于下游 `accounts` 表（不在本 spec 范围）。但 Pusher 投递期间会有以下"投递态"：

```
                ┌─────────────┐
                │   PENDING   │ (Pusher 队列里待发)
                └──────┬──────┘
                       ▼ post
                ┌─────────────┐
                │  IN_FLIGHT  │
                └──────┬──────┘
            ┌──────────┼──────────────┐
            ▼          ▼              ▼
       2xx imported  2xx skipped   4xx/5xx + code
            │          │              │
            ▼          ▼              ▼ (按 FR-008 决策表)
       DELIVERED   DEDUPLICATED   RETRY_LATER / MARK_DEAD / HUMAN_REVIEW
```

> 上面的状态机本身在 Pusher（SPEC-004）实现；本 spec 仅借此说明契约决策点。

---

## 附录 A — 凭据掩码 reference 实现（来自 research.md R6）

### Python

```python
def mask_credential(s: str) -> str:
    if len(s) < 4:
        return '…'
    if len(s) < 12:
        return f"{s[0]}…{s[-1]}"
    return f"{s[:4]}…{s[-4:]}"
```

### Go

```go
func MaskCredential(s string) string {
    n := utf8.RuneCountInString(s)
    rs := []rune(s)
    if n < 4 {
        return "…"
    }
    if n < 12 {
        return fmt.Sprintf("%s…%s", string(rs[0]), string(rs[n-1]))
    }
    return fmt.Sprintf("%s…%s", string(rs[:4]), string(rs[n-4:]))
}
```

两份实现 MUST 对相同输入产出相同字符串（用 ASCII 输入验证；非 ASCII 走"runes 等长"约定）。

---

## 附录 B — `credential_hash` reference 实现

### Python

```python
import hashlib

def canonical_hash(provider: str, auth_type: str, credential: str, refresh_token: str | None = None) -> str:
    c = credential.strip() if credential else (refresh_token or "").strip()
    payload = f"{provider.lower()}\n{auth_type.lower()}\n{c}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

### Go

```go
func CanonicalHash(provider, authType, credential, refreshToken string) string {
    c := strings.TrimSpace(credential)
    if c == "" {
        c = strings.TrimSpace(refreshToken)
    }
    payload := strings.ToLower(provider) + "\n" + strings.ToLower(authType) + "\n" + c
    sum := sha256.Sum256([]byte(payload))
    return hex.EncodeToString(sum[:])
}
```

两份实现 MUST 对相同输入产出**完全相同**的 64 字符 hex。golden-samples.jsonl 中每条都附带预计算的 `credential_hash`，双语 CI 据此核对。
