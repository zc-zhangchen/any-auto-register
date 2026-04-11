# Codex 远程注册机

基于 Browserbase 远程浏览器服务和 DDG 邮箱别名服务的 Codex Token 自动注册工具。

## 功能特点

- 🌐 **远程浏览器**: 使用 Browserbase 提供的远程浏览器服务，无需本地浏览器，不会被风控
- 📧 **DDG 邮箱别名**: 使用 DuckDuckGo 的邮箱别名服务生成临时邮箱
- 🔄 **两阶段注册**:
  - 第一阶段：ChatGPT 账户注册
  - 第二阶段：Codex OAuth 授权

## 环境要求

- Node.js 18+
- 有效的 DDG Token
- 可访问的邮箱收件箱 URL

## 安装

```bash
npm install
```

## 配置

编辑 `config.json` 文件，填入必要参数：

```json
{
  "ddgToken": "your_ddg_token_here",
  "mailInboxUrl": "https://your-mail-inbox-url.com",
  "oauthClientId": "app_EMoamEEZ73f0CkXaXp7hrann",
  "oauthRedirectPort": 1455
}
```

### 配置项说明

| 字段 | 说明 | 必填 |
|------|------|------|
| `ddgToken` | DDG 邮箱别名服务的 Bearer Token | ✅ |
| `mailInboxUrl` | 可被 Browserbase 访问的邮箱收件箱 URL（带 JWT） | ✅ |
| `oauthClientId` | OAuth 客户端 ID | ❌ 默认即可 |
| `oauthRedirectPort` | 本地回调端口 | ❌ 默认 1455 （其实根本不会使用） |

---

## 配置获取教程

### 1. 获取 DDG Token（DuckDuckGo 邮箱别名服务）

DuckDuckGo Email Protection 提供邮箱别名服务，可以生成 `xxx@duck.com` 格式的临时邮箱。

#### 步骤一：安装 DuckDuckGo 浏览器扩展

1. 打开 Chrome 或 Edge 浏览器
2. 访问 [DuckDuckGo Privacy Essentials](https://chrome.google.com/webstore/detail/duckduckgo-privacy-essent/bkdgflcldnnnapblkhphbgpggdiikppg) 扩展页面
3. 点击「添加到 Chrome」安装扩展

#### 步骤二：启用邮箱保护功能

1. 点击浏览器右上角的 DuckDuckGo 图标
2. 在弹出的面板中找到「Email Protection」选项
3. 点击开启并按提示完成设置（需要输入一个邮箱作为转发地址，请使用 `mailInboxUrl` 对应的邮箱）

#### 步骤三：获取 Token

1. 打开浏览器开发者工具（F12）
2. 切换到「Network」标签
3. 在 DuckDuckGo 扩展中点击「Generate New Private Address」或类似按钮
4. 在 Network 列表中找到请求 `https://quack.duckduckgo.com/api/email/addresses`
5. 点击该请求，在「Headers」标签页中找到 `Authorization` 请求头
6. 复制 `Bearer ` 后面的部分，这就是你的 DDG Token

**示例：**
```
Authorization: Bearer 1234567890qwertyuiopasdfghjklzxcvbnm
```

则 Token 为：`Authorization: Bearer 1234567890qwertyuiopasdfghjklzxcvbnm`

#### 验证 Token 是否有效

```bash
curl -X POST https://quack.duckduckgo.com/api/email/addresses \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

成功响应示例：
```json
{"address":"a-b-c"}
```

---

### 2. 获取 mailInboxUrl（Cloudflare 临时邮箱）

由于 Browserbase 远程浏览器需要访问收件箱来获取验证码，你需要使用一个可以从公网访问的临时邮箱服务。推荐使用 Cloudflare Workers 部署的临时邮箱服务。

#### 方案一：使用 Cloudflare Temp Mail（推荐）

1. **Fork 并部署项目**
   - 访问 [dreamhunter2333/cloudflare_temp_email](https://github.com/dreamhunter2333/cloudflare_temp_email)
   - 按照 README 说明部署到 Cloudflare Workers

或者 **使用其他人部署的项目**
   - 比如 [mail.awsl.uk](https://mail.awsl.uk/)

2. **配置邮件地址**
   - 部署完成后，访问你的邮箱域名
   - 点击「创建新邮箱」
   - 复制「打开即可自动登录邮箱的链接」作为 `mailInboxUrl`

#### 方案二：使用其他临时邮箱服务

你也可以使用其他支持公网访问的临时邮箱服务，只要满足以下条件：
- 提供网页界面获取邮件内容
- URL 可以被 Browserbase 远程浏览器访问

---

### 3. OAuth 配置（可选）

`oauthClientId` 和 `oauthRedirectPort` 通常使用默认值即可。如果你需要自定义：

- `oauthClientId`: OpenAI OAuth 应用的客户端 ID
- `oauthRedirectPort`: 本地 OAuth 回调服务监听的端口，确保未被占用

---

## 使用方法

### 单次注册

```bash
node index.js 1
```

### 批量注册

```bash
node index.js 5  # 注册 5 个账户
```

## 工作流程

### 第一阶段：ChatGPT 注册

1. 生成 DDG 邮箱别名
2. 创建 Browserbase 会话
3. 发送 Agent 任务到远程浏览器
4. 监控页面 URL 变化，等待到达完成页面

### 第二阶段：Codex OAuth

1. 生成 OAuth 授权链接
2. 创建新的 Browserbase 会话
3. 发送 Agent 任务进行授权
4. 监控 localhost 回调，提取授权码
5. 用授权码换取 Token 并保存

## 输出文件

Token 文件保存在 `tokens/` 目录下，格式如下：

```json
{
  "access_token": "eyJ...",
  "account_id": "xxx",
  "disabled": false,
  "email": "xxx@duck.com",
  "expired": "2026-03-31T00:00:00+08:00",
  "id_token": "eyJ...",
  "last_refresh": "2026-03-31T00:00:00+08:00",
  "refresh_token": "xxx",
  "type": "codex"
}
```

## 故障排除

### DDG 邮箱生成失败

1. 检查 DDG Token 是否有效
2. 确认 Token 未过期
3. 尝试重新获取 Token

```bash
# 测试 Token
curl -X POST https://quack.duckduckgo.com/api/email/addresses \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 邮箱验证码获取失败

1. 确保 `mailInboxUrl` 可以被 Browserbase 访问
2. 检查 JWT 是否有效（未过期）
3. 确认邮箱地址与发送验证码的地址一致

### Browserbase 连接失败

Browserbase 服务使用的是公开的 Gemini 浏览器服务，如果连接失败：
1. 检查网络连接
2. 确认 `gemini.browserbase.com` 域名可访问

### OAuth 授权失败

1. 确认 `oauthClientId` 正确
2. 检查本地端口 `oauthRedirectPort` 未被占用
3. 查看终端输出的错误信息

## 注意事项

- ⚠️ DDG Token 具有时效性，过期后需要重新获取
- ⚠️ 请合理使用，避免频繁注册触发风控

## 许可证

ISC
