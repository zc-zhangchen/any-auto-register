# Quickstart — PoolItem 中间表示协议

**Branch**: `001-poolitem-contract` | **Date**: 2026-05-13

本文件是**给两侧实现者看的**操作指南。读完即可：(a) 在上游 / 下游各自写出一个最小可用 PoolItem 解析器；(b) 用 curl 演示端到端推送一条；(c) 跑通双语 roundtrip 测试。

> ⚠️ **本 spec 是契约本体，没有可直接 run 的应用**。"完成"由两侧 roundtrip 测试 + 黄金样本字节级对齐定义。下面的代码示例都是参考实现的最小骨架，正式实现由 `/speckit-implement` 阶段产出。

---

## 1. 上游 Python 最小例子（5 分钟跑通）

### 1.1 安装依赖

```bash
cd ~/Projects/any-auto-register
pip install 'pydantic>=2.7'
```

### 1.2 最小 schema（直接拷下面到 `core/pools/schema.py` 就能用）

```python
import hashlib
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal

class PoolItemSource(BaseModel):
    task_id: str
    registered_at: str
    executor: Literal["protocol", "headless", "headed"]
    registrar_version: str | None = None

class PoolItem(BaseModel):
    model_config = ConfigDict(extra='allow')
    schema_version: str = "1.0"
    provider: str
    auth_type: Literal["cookie", "oauth", "apikey"]
    credential: str = ""
    credential_hash: str = Field(min_length=64, max_length=64)
    access_token: str | None = None
    refresh_token: str | None = None
    email: str | None = None
    weight: int | None = None
    proxy_hint: str | None = None
    expires_at: str | None = None
    region: str | None = None
    meta: dict[str, Any] | None = None
    source: PoolItemSource

def canonical_hash(provider: str, auth_type: str, credential: str, refresh_token: str | None = None) -> str:
    c = (credential or "").strip() or (refresh_token or "").strip()
    payload = f"{provider.lower()}\n{auth_type.lower()}\n{c}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

### 1.3 跑一次序列化 + 哈希一致性

```python
src = PoolItemSource(task_id="t-1", registered_at="2026-05-13T03:14:15Z", executor="protocol")
item = PoolItem(
    provider="gpt", auth_type="apikey",
    credential="sk-fake-quickstart",
    credential_hash=canonical_hash("gpt", "apikey", "sk-fake-quickstart"),
    source=src,
)
print(item.model_dump_json(exclude_none=False, by_alias=True))
```

预期输出（缩进示意）：

```json
{"schema_version":"1.0","provider":"gpt","auth_type":"apikey","credential":"sk-fake-quickstart","credential_hash":"<64hex>","access_token":null,"refresh_token":null,"email":null,"weight":null,"proxy_hint":null,"expires_at":null,"region":null,"meta":null,"source":{"task_id":"t-1","registered_at":"2026-05-13T03:14:15Z","executor":"protocol","registrar_version":null}}
```

---

## 2. 下游 Go 最小例子

### 2.1 最小 struct（拷到 `internal/dto/pool_item.go`）

```go
package dto

import (
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "strings"
)

type PoolItemSource struct {
    TaskID           string  `json:"task_id"`
    RegisteredAt     string  `json:"registered_at"`
    Executor         string  `json:"executor"`
    RegistrarVersion *string `json:"registrar_version,omitempty"`
}

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

### 2.2 Roundtrip 单测骨架

```go
// 用 dec.UseNumber() 解码以保留 int64 > 2^53 精度（research.md R3）
func TestRoundtripGoldenSamples(t *testing.T) {
    f, _ := os.Open("testdata/golden-samples.jsonl")
    defer f.Close()
    sc := bufio.NewScanner(f)
    sc.Buffer(make([]byte, 1024*1024), 1024*1024)
    for sc.Scan() {
        line := sc.Bytes()
        if len(line) == 0 || bytes.HasPrefix(line, []byte("//")) { continue }

        dec := json.NewDecoder(bytes.NewReader(line))
        dec.UseNumber()
        var item PoolItem
        if err := dec.Decode(&item); err != nil {
            t.Fatalf("decode: %v", err)
        }
        out, err := json.Marshal(&item)
        if err != nil { t.Fatalf("encode: %v", err) }

        // 字段集合等价性比较：把原 line 与 out 都 normalize 后 SHA-256
        if normalize(line) != normalize(out) {
            t.Fatalf("roundtrip drift:\n in: %s\nout: %s", line, out)
        }
    }
}
```

`normalize` 的实现思路：用 `interface{}` 解 + sort keys + 再 marshal；细节留给 `/speckit-implement` 阶段编写。

---

## 3. 端到端 curl 演示（先看请求 / 响应形状）

### 3.1 lines 模式（兼容历史 `register-to-pool`）

```bash
ADMIN_TOKEN="<8h-bearer>"

curl -s -X POST https://admin.cokeapi.com/admin/api/v1/accounts/import \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "lines",
    "provider": "grok",
    "auth_type": "cookie",
    "text": "eyJfake.sso.grok.01\neyJfake.sso.grok.02"
  }'
```

预期响应：

```json
{"imported":2,"skipped":0,"failed":0,"request_id":"req-abc123"}
```

### 3.2 sub2api 模式（新契约，PoolItem 完整字段）

```bash
curl -s -X POST https://admin.cokeapi.com/admin/api/v1/accounts/import \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "format": "sub2api",
  "accounts": [
    {
      "schema_version": "1.0",
      "provider": "gpt",
      "auth_type": "oauth",
      "credential": "",
      "credential_hash": "<64hex>",
      "access_token": "eyJfake.access",
      "refresh_token": "eyJfake.refresh",
      "email": "user@fake.example",
      "weight": 100,
      "expires_at": "2026-08-13T00:00:00Z",
      "source": {
        "task_id": "t-0001",
        "registered_at": "2026-05-13T03:14:15Z",
        "executor": "protocol",
        "registrar_version": "0.9.0"
      }
    }
  ]
}
JSON
```

预期响应（首次）：

```json
{"imported":1,"skipped":0,"failed":0,"request_id":"req-xyz789"}
```

预期响应（相同 body 重投——验证 FR-009 / SC-003）：

```json
{"imported":0,"skipped":1,"failed":0,"request_id":"req-xyz790"}
```

### 3.3 部分失败示例（验证 FR-008 错误码）

请求里夹一条 `provider="not_yet_registered"`：

```json
{"imported":0,"skipped":0,"failed":1,"errors":[{"index":0,"code":"unknown_provider","message":"provider 'not_yet_registered' is not registered; known: gpt, grok","field":"provider"}]}
```

---

## 4. Admin JWT 懒刷新（来自 research.md R1）

```python
class AdminJWT:
    def __init__(self, login_url, username, password):
        self._login = (login_url, username, password)
        self._token = None
        self._exp = 0  # unix seconds

    def get(self) -> str:
        import time, base64, json, httpx
        if self._token and self._exp - time.time() > 600:    # 距过期 > 10 分钟则复用
            return self._token
        # 否则重新登录
        r = httpx.post(self._login[0], json={"username": self._login[1], "password": self._login[2]}, timeout=10)
        r.raise_for_status()
        tok = r.json()["data"]["token"]
        # 解 JWT exp（不验签，仅取过期时间）
        payload = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "==="))
        self._token, self._exp = tok, int(payload["exp"])
        return self._token
```

**关键不变式**：token 仅在内存；进程结束即丢；不写文件、不入 git。

---

## 5. 凭据掩码用于日志（来自 research.md R6 / data-model.md 附录 A）

```python
def mask_credential(s: str) -> str:
    if len(s) < 4: return '…'
    if len(s) < 12: return f"{s[0]}…{s[-1]}"
    return f"{s[:4]}…{s[-4:]}"
```

> 所有 Pusher 日志、push_logs 表、WebSocket 事件输出凭据字段时 MUST 走这个函数。

---

## 6. 黄金样本说明（`contracts/golden-samples.jsonl`）

- **20 条覆盖**：oauth / cookie / apikey 三种 auth_type、meta 嵌套对象、int64 > 2^53、显式 null、数组、proxy_hint、所有 6 个 provider。
- **`_case` 字段**：仅给人看的标签（如 `01_chatgpt_oauth_full`），解析方 MUST 通过 `extra='allow'` / `json.RawMessage` 忽略；它不在 schema 中、不在 PoolItem 字段定义里、不影响 roundtrip。
- **`credential_hash` 的注意**：jsonl 中预填的 hash 是**形态占位值**（64 hex）而非真实哈希。`/speckit-implement` 阶段产出的"重算并写回 fixture"脚本会把 `credential_hash` 字段重新计算到字节正确，覆盖回 jsonl。两侧 CI 跑测试时 MUST 重算并比对，发现飘移即失败。
- **第 14 条 `schema_version="1.1"` 的 `mfa_seed`**：演示 FR-012 forward-compatibility，v1.0 parser 应忽略未知字段且不报错。

---

## 7. Done 自检 checklist

完成 SPEC-001 之前，两侧必须通过以下检查：

- [ ] 上游 `pytest -k poolitem` 全绿，含 roundtrip + canonical hash 一致性
- [ ] 下游 `go test ./internal/dto/...` 全绿，含同上 + `json.Number` 大整数精度
- [ ] 两侧 fixture (`golden-samples.jsonl`) 的 SHA-256 与 `specs/001-poolitem-contract/contracts/golden-samples.jsonl` 完全一致
- [ ] `contracts/poolitem.schema.json` 通过任一第三方 validator（`ajv-cli` / `python-jsonschema` / `gojsonschema`）对全部 20 条 fixture 校验通过
- [ ] PR 中的"Constitution Check"表 6 项全部 ✅ 或 JUSTIFIED
- [ ] `gpt2apiup/docs/04-API规范.md` 已同步 `format=sub2api` 与新错误码表（虽然完整下游实现是 SPEC-002，但 API 文档应在本 spec 合并时同步）

满足全部 7 项即 SPEC-001 done。失败任一项不得标记 done。
