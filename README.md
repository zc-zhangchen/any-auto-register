# Any Auto Register

<p align="center">
  <a href="https://linux.do" target="_blank">
    <img src="https://img.shields.io/badge/LINUX-DO-FFB003?style=for-the-badge&logo=linux&logoColor=white" alt="LINUX DO" />
  </a>
</p>

> ⚠️ 免责声明：本项目仅供学习与研究使用，不得用于任何商业用途。使用本项目所产生的一切后果由使用者自行承担。

<p align="center">
  <a href="README.md">中文</a> |
  <a href="README_en.md">English</a> |
  <a href="README_vi.md">Tiếng Việt</a>
</p>

多平台账号自动注册与管理系统，支持插件化扩展、Web UI 管理、批量注册、状态同步，以及本地 Turnstile Solver 自动拉起。

## 目录

- [当前界面与实际平台展示](#当前界面与实际平台展示)
- [功能特性](#功能特性)
- [自营产品](#自营产品)
- [赞助商目录](#赞助商目录)
- [界面预览](#界面预览)
- [技术栈](#技术栈)
- [环境要求](#环境要求)
- [ChatGPT 专项能力](#chatgpt-专项能力)
- [邮箱服务支持](#邮箱服务支持)
- [快速开始](#快速开始)
- [Docker 部署](#docker-部署)
- [插件与外部依赖](#插件与外部依赖)
- [常见问题排查](#常见问题排查)
- [更新记录](#更新记录)
- [项目结构](#项目结构)
- [Electron 开发说明](#electron-开发说明)
- [用户讨论群](#用户讨论群)
- [打赏博主](#赞助支持)
- [Star History](#star-history)
- [License](#license)

## 当前界面与实际平台展示

根据当前前端代码与界面，**左侧“平台管理”菜单默认显示的平台**为：

- ChatGPT
- iCloud（Hide My Email 隐私邮箱）

## 功能特性

- **多平台账号注册与管理**：统一的账号列表、详情、导入、多格式导出、删除、批量操作
- **iCloud 隐私邮箱**：Apple ID 主号登录（SRP + 双重认证 / Cookie 导入）、Hide My Email 批量生成与收件箱查看
- **多执行器模式**：纯协议、无头浏览器、有头浏览器
- **多邮箱服务接入**：支持内置、第三方、自建 Worker 邮箱等多种方案
- **验证码支持**：YesCaptcha、本地 Turnstile Solver（Camoufox）
- **手机接码**：SmsBower / HeroSMS 自动租号收码，ChatGPT 命中 add-phone 时全程无人值守
- **代理能力**：代理池轮询、代理状态维护、注册过程代理接入
- **批量注册**：支持注册数量、并发数、每个账号启动延迟设置
- **实时日志**：前端实时查看注册日志
- **任务历史管理**：支持历史记录查看与批量删除
- **插件化扩展**：可按需接入外部服务和独立管理端

## 自营产品

感谢以下自营产品对 any-auto-register 的支持。

| Logo | 名称 | 介绍 | 官网 |
| --- | --- | --- | --- |
| <a href="https://faka.gsyun.cloud/" target="_blank"><img src="frontend/public/logo.png" alt="阿晨小铺" width="140" /></a> | 阿晨小铺 | 本人经营gpt等虚拟产品,诚信稳定，有保障 | [https://faka.gsyun.cloud/](https://faka.gsyun.cloud/) |
| <a href="https://api.codelife.eu.cc/" target="_blank">zc-api</a> | zc-api | 面向 Claude Code、Codex 等模型调用场景的中转服务，10G 带宽保障首字响应更快、链路稳定。提供高可用接口、便捷接入与持续交付支持，适合开发者与团队长期使用；支持开具发票，详情可前往官网查看。 | [https://api.codelife.eu.cc/](https://api.codelife.eu.cc/) |

## 赞助商目录

感谢以下朋友与伙伴对 any-auto-register 的支持。

| Logo | 名称 | 介绍 | 官网 |
| --- | --- | --- | --- |
| <a href="https://www.rapidproxy.io/?code=IFZZROPF1" target="_blank"><img src="frontend/public/RapidProxy.png" alt="RapidProxy" width="140" /></a> | RapidProxy | RapidProxy 为自动化注册与账号管理场景提供稳定的代理支持。<br><br>RapidProxy 提供全球住宅 IP 网络，支持智能轮换、稳定 Session 和高并发请求，帮助开发者更高效地完成批量任务，优化自动化执行环境。<br><br>动态住宅代理低至 $0.55/GB，流量长期有效不过期。<br><br>**适用场景：**<br>自动化注册 / 浏览器自动化（Playwright、Selenium）/ 多账号环境管理 / 数据采集任务<br><br>注册可送 500MB 免费测试，邀请好友即可赚取高达 15% 的佣金！<br><br>**专属优惠码：RAPID10（优惠 10%）** | [https://www.rapidproxy.io/?code=IFZZROPF1](https://www.rapidproxy.io/?code=IFZZROPF1) |
| <a href="https://www.ipwo.net/?ref=githubanyautoregister" target="_blank"><img src="frontend/public/ipwo.png" alt="IPWO" width="140" /></a> | IPWO | IPWO 住宅代理适用于浏览器自动化、多地区网络访问、数据采集及在线业务测试等场景。<br><br>对于 any-auto-register 这类涉及浏览器自动化、代理池管理和多环境运行的项目，IPWO 住宅代理可用于配置不同浏览器会话的网络环境，支持灵活的 IP 切换与地区选择，为自动化任务提供更加便捷的代理接入方式。<br><br>提供 195+ 地区动静态 IP 资源，支持 http/https/socks5 协议，免费测试。<br><br>**专属优惠码：0204（优惠 10%）** | [https://www.ipwo.net/?ref=githubanyautoregister](https://www.ipwo.net/?ref=githubanyautoregister) |

## 界面预览

### 仪表盘

![仪表盘](docs/images/dashboard.png)

### 全局配置 / 插件管理

![全局配置 / 插件管理](docs/images/settings-integrations.png)

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | FastAPI + SQLite（SQLModel） |
| 前端 | React + TypeScript + Vite |
| HTTP | curl_cffi |
| 浏览器自动化 | Playwright / Camoufox |
| ChatGPT 注册协议 | 纯协议实现，Sentinel PoW 走 Node 沙箱 |

## 环境要求

- Python 3.12+
- Node.js 18+（既用于构建前端，也是 ChatGPT Sentinel PoW 求解器的运行时，**注册时必须可执行**）
- Conda（推荐）
- Windows（推荐直接使用仓库内启动脚本）

## ChatGPT 专项能力

当前版本里，**ChatGPT 是功能最完整的平台之一**，不仅支持注册，还支持 Token 生命周期管理、状态探测和外部系统同步。

### 1. 注册协议

ChatGPT 的整条注册链路位于 `platforms/chatgpt/protocol/`，是**纯协议实现，不需要浏览器**：

- `http_client.py` —— 基于 `curl_cffi` 的 TLS 指纹会话
- `auth_flow.py` —— 驱动 OpenAI authorize 状态机（注册、OTP、add-phone、Codex OAuth）
- `sentinel_quickjs.py` + `openai_sentinel_quickjs.js` —— 在 Node 沙箱里跑 OpenAI 真实的 `sdk.js` 求解 Sentinel PoW

> ⚠️ **Sentinel 需要 Node 运行时。** 自己合成的 PoW token 能骗过 `/sentinel/req` 的表层校验，但发码服务会在服务端复核，结果是验证码邮件被静默丢弃——链路看着一切正常却永远收不到码。所以必须有可执行的 `node`（>= 18），如果不在 `PATH` 里可用 `OPENAI_SENTINEL_NODE_PATH` 指定绝对路径。

协议层之上只有三个注入点：邮箱池适配器（`protocol/mailbox_adapter.py`）、手机接码控制器（`services/sms_service.py`）、密码生效回调。任务级配置通过实例参数下传，**不写进程环境变量**，因此多个注册任务并发时互不干扰。

### 2. ChatGPT Token 方案切换

前端当前提供两种 ChatGPT 注册模式：

- **有 RT**（默认推荐）
  - 完整跑一遍 Codex OAuth
  - 产出 **Access Token + Refresh Token**
- **无 RT**
  - 跳过 Codex OAuth（每次省约 10 秒）
  - 仅产出 **Access Token / Session**
  - 依赖 RT 的后续能力可能不可用

这项切换在以下位置都能看到：

- 注册任务页
- ChatGPT 平台注册弹窗

### 3. ChatGPT 注册方式

同样两个位置还能选注册用什么身份，和上面的 Token 方案可以任意组合：

- **邮箱注册**（默认）
  - 从邮箱池领地址，收邮件验证码
- **手机注册**
  - 从接码平台租号，收短信验证码，不占用邮箱
  - 账号在列表里以手机号为标识
- **手机注册 + 绑定邮箱**
  - 先用号码注册，再把邮箱池里的地址绑到账号上，收一次邮件验证码
  - 绑定成功后账号按邮箱记账，手机号留在账号详情里

后两种都要先在「设置 → 手机接码」里启用接码并填好 API Key，否则任务会直接报错。绑定邮箱这一步只在 OpenAI 把 add-email 摆进当前 authorize 流程时才会被接受；被拒时账号照常保留，失败原因记在账号详情里，可以稍后单独补绑。

### 4. TOTP 2FA 绑定

注册任务页和 ChatGPT 注册弹窗上还有一个「绑定 2FA」开关，**默认关闭**。打开后注册成功的号会顺手绑上一个 TOTP 双因素：

- **快路径**：复用注册那条会话直接申请密钥并激活。注册链几十秒前才做完验证，服务端认这是「最近认证过」，所以不用重新登录、不用再收一封邮件，几秒钟完事。
- **慢路径**：快路径没成时才走，用邮箱 + 密码重跑一遍登录正式链再绑，要多花一次 PoW，多半还要收一封验证码邮件。手机号身份的号没有邮箱可登，会跳过这一步。

密钥随号落库（写进账号 `extra` 的 `totp_secret`），三个地方都能复制导入验证器 App：账号列表里点「2FA 已绑」标签、账号操作菜单里的「复制 2FA 密钥」、账号详情里的密钥栏。补绑动作跑完的弹窗也会把密钥单独列出来带复制按钮，任务日志里同样打一遍。批量拿密钥用导出里的 `邮箱----密码----2FA` 之类的格式。

库里的老号可以在账号操作菜单里点「绑定 2FA」单独补绑，同样先试复用会话、会话失效再走重新登录。这个动作和「补 RT」一样跑成后台任务：点完立刻弹出日志窗口，实时看到走的是哪条路、是不是在等验证码，也能中途停掉；绑成功那一刻密钥会打在日志里，弹窗顶部再单独列一份带复制按钮。

> ⚠️ 密钥只在绑定那一刻由服务端下发一次，任何接口都取不回。绑定即生效，之后该号每次登录都要动态码 —— 补 RT、重新登录这些链路会自动用库里的密钥算码通过，但密钥丢了这个号就再也登不进去。

### 5. 手机接码（add-phone）

OpenAI 会对部分注册请求要求绑定手机号。命中 add-phone 时，系统会自动租号、等短信、提交验证码，全程无人值守。在「设置 → 手机接码」里配置：

| 配置项 | 说明 |
| --- | --- |
| 启用手机接码 | 关闭时命中 add-phone 会回退到手工号码路径（`OPENAI_PHONE_NUMBER`） |
| 接码平台 | SmsBower / HeroSMS，两家共用 sms-activate 的 `handler_api.php` 协议 |
| API Key | 平台密钥，可用页面上的「测试余额」直接自检 |
| 服务代码 | 平台按服务码分库存，OpenAI 对应 `dr` |
| 默认国家 ID | 默认 `52`（泰国） |
| 自动选最优国家 | 按价格升序 + 库存挑号；也可用「允许的国家」限定候选范围 |
| 复用同一号码 | 在号码 20 分钟租期内复用，直到达到单号成功次数上限 |
| 单号等待秒数 / 最多换号次数 / 单号内验证重试次数 | 收码失败时的重试策略 |

「查询国家排名」会列出该服务码下各国的价格与库存，绿色标签是 OpenAI 走纯短信的国家。

> ⚠️ OpenAI 自 2025 年起对大部分国家改用 WhatsApp 验证，纯 SMS 路径实测只有**泰国（country_id=52）**稳定可用。选其它国家可能抽到 WhatsApp 号从而收不到短信，自动选号时会打告警但不阻止。

国家 ID、单号等待秒数、最多换号次数还可以在注册任务页按任务覆盖，平台与 API Key 只在全局配置里维护。

### 6. ChatGPT 批量状态同步与补传

在 ChatGPT 平台列表顶部，当前还有两类批量能力：

- **状态同步**
  - 同步所选账号本地状态
  - 同步所选账号 CLIProxyAPI 状态
  - 或对当前筛选结果批量执行
- **补传远端未发现**
  - 补传远端未发现的 auth-file
  - 支持“当前筛选范围”或“当前所选账号”两种作用范围

### 7. 多格式批量导出

账号列表右上角的「导出」打开导出弹窗：先选范围（勾选的账号 / 当前筛选出的全部账号，翻页不影响），再选格式，右边直接出预览，然后一键复制或下载。

| 格式 | 一行长什么样 |
| --- | --- |
| `email_pw` | `邮箱----密码` |
| `email_pw_2fa` | `邮箱----密码----2FA 密钥` |
| `email_pw_2fa_at` | 再接 `----AccessToken` |
| `email_pw_2fa_rt` | 再接 `----RefreshToken` |
| `email_pw_2fa_at_rt` | 登录与调用凭证一次带齐 |
| `email_pw_2fa_phone` | 再接 `----手机号` |
| `email_pw_rt` | `邮箱----密码----RefreshToken` |
| `email_2fa` | `邮箱----2FA 密钥` |
| `at` / `rt` / `totp` | 一行一个 token，没有该字段的账号自动跳过 |
| `csv` / `json` | 全字段，给 Excel 或脚本用 |

空字段照样占位（`a@b.com----pw----` 结尾那个分隔符不会省），按 `----` 切列的脚本不会错位。格式清单由后端 `services/account_export.py` 的 `EXPORT_FORMATS` 统一定义，加一个新格式只改这一处，前端下拉框自动跟上。

## 邮箱服务支持

根据当前注册页实际配置项，项目支持以下邮箱服务：

| 服务名称 | 标识 | 说明 |
| --- | --- | --- |
| LuckMail | `luckmail` | 可免费领取用于测试，且**每天签到还能继续领取邮箱** |
| MoeMail | `moemail` | 默认常用方案，自动注册账号并生成邮箱 |
| TempMail.lol | `tempmail_lol` | 临时邮箱方案，部分地区可能需要代理 |
| SkyMail (CloudMail) | `skymail` | 通过 API / Token / 域名使用 |
| YYDS Mail / MaliAPI | `maliapi` | 支持域名与自动域名策略 |
| GPTMail | `gptmail` | 基于 GPTMail API 生成临时邮箱并轮询邮件，支持已知域名时本地拼装随机地址 |
| DuckMail | `duckmail` | 临时邮箱方案 |
| Freemail | `freemail` | 自建邮箱服务 |
| Laoudo | `laoudo` | 固定邮箱方案 |
| CF Worker | `cfworker` | Cloudflare Worker 自建邮箱 |

### iCloud 隐私邮箱说明

iCloud 平台不消耗上表中的临时邮箱池，而是使用 Apple 自带的 Hide My Email 地址：

1. 在「iCloud 隐私邮箱 → 主号管理」中添加 Apple ID 主号，支持两种方式：
   - **账号密码登录**：走 Apple SRP 协议，按需完成双重认证（可信设备推送或短信验证码）；
   - **Cookie 导入**：直接粘贴浏览器导出的 iCloud Cookie。
2. 登录成功后在「隐私邮箱」标签页批量生成别名，Apple 侧限制为**每小时最多 5 个**，系统会按主号维度自行限流。
3. 主号的 IMAP 密码（应用专用密码）用于拉取别名收件箱，凭据均以 AES-256-GCM 加密后落库。

加密密钥取自环境变量 `CREDENTIAL_ENCRYPTION_KEY`；未设置时会在 `.secrets/credential_key` 自动生成一份本地密钥。

## 快速开始

### 1. 创建并激活 Conda 环境

```bash
conda create -n any-auto-register python=3.12 -y
conda activate any-auto-register
```

### 2. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 3. 安装浏览器相关依赖

```bash
python -m playwright install chromium
python -m camoufox fetch
```

### 4. 安装并构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

构建完成后，静态资源输出到：

```text
./static
```

### 5. 启动项目

#### Windows 推荐方式

PowerShell：

```powershell
.\start_backend.ps1
```

CMD：

```bat
start_backend.bat
```

#### 手动启动

```bash
conda activate any-auto-register
python main.py
```

启动后默认访问：

```text
http://localhost:8000
```

> 如果你已经执行过 `npm run build`，前端会由 FastAPI 直接托管，因此访问的是 `8000`，不是 `5173`。

## Windows 启动脚本说明

仓库内已提供以下脚本：

- `start_backend.bat`
- `start_backend.ps1`
- `stop_backend.bat`
- `stop_backend.ps1`

这些脚本会强制使用 `any-auto-register` 环境启动/停止后端，可避免以下常见问题：

- 后端能启动，但 Solver 没有拉起
- `ModuleNotFoundError: quart`
- 前端中 Turnstile Solver 一直显示“未运行”

停止服务时可执行：

PowerShell：

```powershell
.\stop_backend.ps1
```

CMD：

```bat
stop_backend.bat
```

默认会停止：

- 后端端口：`8000`
- Solver 端口：`8889`

## 前端开发模式

适合调试 React 页面时使用。

### 终端 1：启动后端

```powershell
.\start_backend.ps1
```

### 终端 2：启动 Vite

```bash
cd frontend
npm run dev
```

访问地址：

```text
http://localhost:5173
```

Vite 会将 `/api` 请求代理到本地后端 `http://localhost:8000`。

## Turnstile Solver 说明

### 自动启动

本地 Turnstile Solver 会在 FastAPI 后端启动时自动拉起，默认地址：

```text
http://localhost:8889
```

前端“全局配置 → 验证码 → Turnstile Solver”显示的是**后端检测结果**，因此：

- 后端未启动 → 前端显示“未运行”
- 后端已启动但不在正确 conda 环境 → Solver 可能启动失败

### 手动启动 Solver

```bash
conda activate any-auto-register
python services/turnstile_solver/start.py --browser_type camoufox --port 8889
```

### Solver 日志

如启动失败，可查看：

```text
services/turnstile_solver/solver.log
```

## Docker 部署

仓库根目录已提供两套：

| 用途 | 文件 | 镜像体积 | 说明 |
| --- | --- | --- | --- |
| 完整版（含浏览器） | `Dockerfile` + `docker-compose.yml` | 约 5GB | 带 Playwright / Camoufox / Turnstile Solver |
| 无头服务器 | `Dockerfile.server` + `docker-compose.server.yml` | 约 1.1GB | 只跑 Web UI 与 ChatGPT/iCloud 注册，不装浏览器栈 |

ChatGPT 切到纯协议后两个平台都不用浏览器，服务器部署推荐用无头版，详见
[docs/SERVER_DEPLOY.md](docs/SERVER_DEPLOY.md)（含反向代理配置和**必须先设登录密码**的说明）。

以下是完整版的部署内容：

- FastAPI 后端
- 已构建的前端静态资源
- SQLite 数据库持久化目录 `./data`
- 随后端自动拉起的本地 Turnstile Solver

### 启动

```bash
docker compose up -d --build
```

首次构建会额外下载 Python 依赖、Playwright Chromium 和 Camoufox，因此耗时会明显更长。

当前 Dockerfile 已改为通过固定直链安装 Camoufox，以避免构建时访问 GitHub Releases API 触发匿名限流。

### 下载预构建镜像并运行（可选）

如果你不想在本地构建，也可以直接拉取 GitHub Actions 产出的镜像运行。

镜像仓库（原项目）：

```text
ghcr.io/zc-zhangchen/any-auto-register:latest
```

拉取镜像：

```bash
docker pull ghcr.io/zc-zhangchen/any-auto-register:latest
```

运行容器（与 compose 挂载目录保持一致）：

```bash
docker run -d \
  --name any-auto-register \
  -p 8000:8000 \
  -p 127.0.0.1:8889:8889 \
  -v ./data:/runtime \
  -v ./_ext_targets:/_ext_targets \
  -v ./external_logs:/app/services/external_logs \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  -e APP_ENABLE_SOLVER=1 \
  ghcr.io/zc-zhangchen/any-auto-register:latest
```

如果镜像访问受限，可先登录 GHCR：

```bash
docker login ghcr.io
```

### 访问

```text
http://localhost:8000
```

### 停止

```bash
docker compose down
```

### 查看日志

```bash
docker compose logs -f app
```

### 数据持久化

容器默认使用：

```text
DATABASE_URL=sqlite:////app/data/account_manager.db
```

宿主机会挂载到：

```text
./data
```

### 常用环境变量

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | FastAPI 监听地址 |
| `PORT` | `8000` | FastAPI 监听端口 |
| `DATABASE_URL` | `sqlite:////app/data/account_manager.db` | SQLite 数据库地址 |
| `APP_ENABLE_SOLVER` | `1` | 是否自动启动本地 Solver，设为 `0` 可禁用 |
| `SOLVER_PORT` | `8889` | Solver 监听端口 |
| `LOCAL_SOLVER_URL` | `http://127.0.0.1:8889` | 后端访问 Solver 的地址 |
| `OPENAI_SENTINEL_NODE_PATH` | `node` | Sentinel PoW 求解器使用的 Node 可执行文件，`node` 不在 `PATH` 时填绝对路径 |

如需传入 `OPENAI_*` 等配置，可直接写入仓库根目录 `.env` 文件，`docker compose` 会自动注入到容器环境中。

### Camoufox 构建参数

如需覆盖上游版本，可在构建时指定：

```bash
CAMOUFOX_VERSION=135.0.1 CAMOUFOX_RELEASE=beta.24 docker compose build app
```

### Docker 使用建议

- 当前 Docker 镜像主要覆盖主应用和本地 Turnstile Solver
- `CLIProxyAPI` 的自动安装/拉起逻辑仍偏向宿主机环境
- 若依赖 `conda`、Go 或 Windows 可执行文件，不建议直接在当前 Linux 容器中启动这些插件
- 如果你只需要 Web UI、账号管理、任务调度和本地 Solver，当前 Compose 配置可直接使用

## 插件与外部依赖

### 临时邮箱方案来源

项目支持 Cloudflare Worker 自建临时邮箱，当前使用方案来源于：

- <https://github.com/dreamhunter2333/cloudflare_temp_email>

### 外部插件 Git 地址

项目当前支持按需安装/启动以下外部组件：

| 项目 | 用途 | Git 地址 |
| --- | --- | --- |
| CLIProxyAPI | CPA / 代理池管理服务 | `https://github.com/router-for-me/CLIProxyAPI.git` |

插件页中的 **“安装最新版 / 更新到最新版”** 会同步仓库最新代码，且已支持 **卸载**（会先停止服务，再删除本地插件目录）。
默认按 **最新 semver tag** 更新；你也可以在“设置 → 插件 → 安装/更新策略”切回 **分支 HEAD** 模式。

如果你后续要改成 `ghproxy`、`gitclone`、企业 Git 镜像或其他代理地址，需要同步修改：

```text
services/external_apps.py
```

## 常见问题排查

### 1. 前端里 Turnstile Solver 显示“未运行”

先检查后端是否正常启动：

```bash
curl http://localhost:8000/api/solver/status
```

正常返回示例：

```json
{"running":true}
```

如果 `8000` 端口都访问不到，说明问题在后端，而不是 Solver 本身。

### 2. 出现 `ModuleNotFoundError: quart`

说明当前启动后端的 Python 不是 `any-auto-register` 环境，请改用：

```powershell
.\start_backend.ps1
```

或：

```bat
start_backend.bat
```

### 3. 如何确认当前 Python 是否正确

```bash
python -c "import sys; print(sys.executable)"
```

输出应类似：

```text
D:\miniconda\conda3\envs\any-auto-register\python.exe
```

### 4. Solver 能打开，但状态仍然异常

检查以下两个地址：

```text
http://localhost:8000/api/solver/status
http://localhost:8889/
```

如果第二个能打开、但第一个不通，问题就在后端，不在 Solver。

### 5. 端口被占用

如果启动时报 `WinError 10048`，先执行：

```powershell
.\stop_backend.ps1
```

然后重新启动：

```powershell
.\start_backend.ps1
```

### 6. ChatGPT 注册收不到验证码

先确认 `node` 可执行：

```bash
node --version
```

Sentinel PoW 求解器要在 Node 沙箱里跑 OpenAI 的 `sdk.js`，没有 Node 时算出来的 token 过不了服务端复核，**验证码邮件会被静默丢弃**——日志上看不到明显报错，但码永远收不到。若 `node` 不在 `PATH` 里，用 `OPENAI_SENTINEL_NODE_PATH` 指定绝对路径。

## 更新记录

### 2026-08-28

- 优化代理池对 `host:port:user:pass` 格式的兼容性，代理检测与浏览器执行器会使用一致的规范化代理配置。
- 代理健康统计现在能准确回写到原始代理记录；检测成功会自动恢复启用，从未成功且连续失败的代理会自动停用。

完整历史请查看 [docs/releases/release-notes.md](docs/releases/release-notes.md)。

## 项目结构

```text
any-auto-register/
├── api/
├── core/
├── docs/
├── electron/
├── frontend/
├── platforms/
├── services/
│   ├── solver_manager.py
│   └── turnstile_solver/
├── static/
├── tests/
├── main.py
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── start_backend.bat
├── start_backend.ps1
├── stop_backend.bat
└── stop_backend.ps1
```

## Electron 开发说明

Electron 开发模式不会自动启动 Python 后端。

请先在项目根目录启动：

```powershell
.\start_backend.ps1
```

然后再运行 Electron。

## 用户讨论群

- QQ群：**1065114376**（any-auto-register 注册机用户讨论群）

## 赞助支持

如果这个项目对你有帮助，欢迎赞助支持项目继续维护与更新。

![打赏码](docs/images/dashang.JPG)

## Star History

<a href="https://star-history.dera.page/#zc-zhangchen/any-auto-register&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://star-history.dera.page/image?repos=zc-zhangchen/any-auto-register&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://star-history.dera.page/image?repos=zc-zhangchen/any-auto-register&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://star-history.dera.page/image?repos=zc-zhangchen/any-auto-register&type=date&legend=top-left" />
 </picture>
</a>

## License

MIT License — 仅供学习研究，禁止商业使用。
