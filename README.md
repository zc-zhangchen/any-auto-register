# Any Auto Register

<p align="center">
  <a href="https://linux.do" target="_blank">
    <img src="https://img.shields.io/badge/LINUX-DO-FFB003?style=for-the-badge&logo=linux&logoColor=white" alt="LINUX DO" />
  </a>
</p>

> ⚠️ 免责声明：本项目仅供学习与研究使用，不得用于任何商业用途。使用本项目所产生的一切后果由使用者自行承担。

多平台账号自动注册与管理系统，支持插件化扩展、Web UI 管理、批量注册、状态同步，以及本地 Turnstile Solver 自动拉起。

## 目录

- [项目简介](#项目简介)
- [当前界面与实际平台展示](#当前界面与实际平台展示)
- [功能特性](#功能特性)
- [界面预览](#界面预览)
- [技术栈](#技术栈)
- [环境要求](#环境要求)
- [ChatGPT 专项能力](#chatgpt-专项能力)
- [邮箱服务支持](#邮箱服务支持)
- [快速开始](#快速开始)
- [Docker 部署](#docker-部署)
- [插件与外部依赖](#插件与外部依赖)
- [常见问题排查](#常见问题排查)
- [项目结构](#项目结构)
- [Electron 开发说明](#electron-开发说明)
- [用户讨论群](#用户讨论群)
- [赞助商目录](#赞助商目录)
- [打赏博主](#赞助支持)
- [Star History](#star-history)
- [License](#license)

## 项目简介

本项目基于 [lxf746/any-auto-register](https://github.com/lxf746/any-auto-register.git) 二次开发

## 当前界面与实际平台展示

根据当前前端代码与界面，**左侧“平台管理”菜单默认显示的平台**为：

- ChatGPT
- Grok
- Kiro (AWS Builder ID)
- OpenBlockLabs
- Trae.ai



## 功能特性

- **多平台账号注册与管理**：统一的账号列表、详情、导入、导出、删除、批量操作
- **多执行器模式**：纯协议、无头浏览器、有头浏览器
- **多邮箱服务接入**：支持内置、第三方、自建 Worker 邮箱等多种方案
- **验证码支持**：YesCaptcha、本地 Turnstile Solver（Camoufox）
- **代理能力**：代理池轮询、代理状态维护、注册过程代理接入
- **批量注册**：支持注册数量、并发数、每个账号启动延迟设置
- **实时日志**：前端实时查看注册日志
- **任务历史管理**：支持历史记录查看与批量删除
- **插件化扩展**：可按需接入外部服务和独立管理端

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

## 环境要求

- Python 3.12+
- Node.js 18+ / pnpm 10+
- uv（推荐）或 Conda（兼容旧流程）
- Windows（推荐直接使用仓库内启动脚本）

## ChatGPT 专项能力

当前版本里，**ChatGPT 是功能最完整的平台之一**，不仅支持注册，还支持 Token 生命周期管理、状态探测和外部系统同步。

### 1. ChatGPT Token 方案切换

前端当前提供两种 ChatGPT 注册模式：

- **有 RT**（默认推荐）
  - 走新 PR 链路
  - 产出 **Access Token + Refresh Token**
- **无 RT**（兼容旧方案）
  - 走旧链路
  - 仅产出 **Access Token / Session**
  - 依赖 RT 的后续能力可能不可用

这项切换在以下位置都能看到：

- 注册任务页
- ChatGPT 平台注册弹窗



### 4. ChatGPT 批量状态同步与补传

在 ChatGPT 平台列表顶部，当前还有两类批量能力：

- **状态同步**
  - 同步所选账号本地状态
  - 同步所选账号 CLIProxyAPI 状态
  - 或对当前筛选结果批量执行
- **补传远端未发现**
  - 补传远端未发现的 auth-file
  - 支持“当前筛选范围”或“当前所选账号”两种作用范围

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
| Cloudflare 邮件路由 | `cfrouting` | 不走 Worker；假设你已在 Cloudflare 配好邮件路由转发，本项目只负责生成别名并直接轮询目标邮箱 IMAP，目标邮箱可用 QQ 或个人 Gmail |

### Cloudflare 邮件路由（QQ / Gmail）

`cfrouting` 的思路是：

- Cloudflare 负责把 `随机别名@你的域名` 转发到你的真实邮箱
- 本项目只负责生成别名，并通过 IMAP 去真实邮箱里抓验证码

常见填写方式：

- QQ 邮箱
  - `IMAP Server`: `imap.qq.com`
  - `IMAP Port`: `993`
  - `用户名`: 你的 QQ 邮箱完整地址
  - `密码`: QQ 邮箱授权码
- 个人 Gmail
  - `IMAP Server`: `imap.gmail.com`
  - `IMAP Port`: `993`
  - `用户名`: 你的 Gmail 完整地址
  - `密码`: Google App Password

说明：

- 个人 Gmail 不必先接 OAuth；对本项目这种普通 IMAP 登录，通常直接使用 `App Password` 即可。
- QQ 和 Gmail 都建议先把 `轮询文件夹` 留成 `INBOX`，确认邮件实际落点后再调整。
- 如果你已经确认 QQ 网页端能很快看到邮件，但 IMAP 抓取明显滞后，优先考虑改用 Gmail 作为 Cloudflare 转发目标。
| DuckMail | `duckmail` | 临时邮箱方案 |
| Freemail | `freemail` | 自建邮箱服务 |
| Laoudo | `laoudo` | 固定邮箱方案 |
| CF Worker | `cfworker` | Cloudflare Worker 自建邮箱 |

### Kiro 邮箱说明

Kiro 当前风控较严格，邮箱方案会显著影响成功率。当前项目内也保留了这条重点提示：

- **自建邮箱成功率：100%**
- **项目内置临时邮箱成功率：0%**

因此进行 **Kiro (AWS Builder ID)** 注册时，建议优先使用**自建邮箱**。

## 快速开始

### 1. 安装并同步后端依赖（uv）

```bash
uv python install 3.12
uv sync
```

项目现已提供 `pyproject.toml` 和 `uv.lock`，后续新增 Python 依赖请优先使用：

```bash
uv add <package>
```

不要再使用 `uv pip install`。

### 2. 安装浏览器相关依赖

```bash
uv run python -m playwright install chromium
uv run python -m camoufox fetch
```

### 3. 安装并构建前端

如本机还没有 `pnpm`，可先执行：

```bash
corepack enable
```

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
```

构建完成后，静态资源输出到：

```text
./static
```

### 4. 启动项目

#### Windows 推荐方式

PowerShell：

```powershell
.\start_backend.ps1
```

CMD：

```bat
start_backend.bat
```

这两个脚本会优先使用仓库根目录下由 `uv sync` 创建的 `.venv`；如果 `.venv` 不存在，再回退到 `any-auto-register` 这个 conda 环境。

#### 手动启动

```bash
uv run python main.py
```

启动后默认访问：

```text
http://localhost:8000
```

> 如果你已经执行过 `pnpm --dir frontend build`，前端会由 FastAPI 直接托管，因此访问的是 `8000`，不是 `5173`。

## Windows 启动脚本说明

仓库内已提供以下脚本：

- `start_backend.bat`
- `start_backend.ps1`
- `stop_backend.bat`
- `stop_backend.ps1`

这些脚本会优先使用仓库根目录 `.venv`，否则回退到 `any-auto-register` conda 环境启动/停止后端，可避免以下常见问题：

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
pnpm --dir frontend dev
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
- 后端已启动但不在正确 `.venv` / conda 环境 → Solver 可能启动失败

### 手动启动 Solver

```bash
uv run python services/turnstile_solver/start.py --browser_type camoufox --port 8889
```

### Solver 日志

如启动失败，可查看：

```text
services/turnstile_solver/solver.log
```

## Docker 部署

仓库根目录已提供：

- `Dockerfile`
- `docker-compose.yml`

默认部署内容包括：

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

如需传入 `SMSTOME_COOKIE`、`OPENAI_*` 等配置，可直接写入仓库根目录 `.env` 文件，`docker compose` 会自动注入到容器环境中。

### Camoufox 构建参数

如需覆盖上游版本，可在构建时指定：

```bash
CAMOUFOX_VERSION=135.0.1 CAMOUFOX_RELEASE=beta.24 docker compose build app
```

### Docker 使用建议

- 当前 Docker 镜像主要覆盖主应用和本地 Turnstile Solver
- `grok2api`、`CLIProxyAPI`、`Kiro Account Manager` 的自动安装/拉起逻辑仍偏向宿主机环境
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
| grok2api | Grok token 管理、回填、聊天/API 服务 | `https://github.com/chenyme/grok2api.git` |
| kiro-account-manager | Kiro 账号管理相关插件 | `https://github.com/hj01857655/kiro-account-manager.git` |

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

说明当前启动后端的 Python 不是仓库 `.venv` 或 `any-auto-register` conda 环境，请改用：

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
D:\github\any-auto-register\.venv\Scripts\python.exe
```

或：

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

## 赞助商目录

感谢以下朋友与伙伴对 any-auto-register 的支持。

| Logo | 名称 | 介绍 | 官网 |
| --- | --- | --- | --- |
| <a href="https://gzxsy.vip" target="_blank"><img src="frontend/public/gzxsylogo.jpg" alt="星思研中转站" width="140" /></a> | 星思研中转站 | 为 Claude Code、Codex 等模型调用场景提供稳定中转与配套服务，适合需要高可用接口、便捷接入和持续交付支持的开发者与团队。可前往官网了解最新方案。 | [https://gzxsy.vip](https://gzxsy.vip) |
| <a href="https://ai.xiaoye.io/" target="_blank"><img src="frontend/public/xiaoyelogo.jpg" alt="小野API中转站" width="140" /></a> | 小野API中转站 | 为 Claude Code、Codex 等模型调用场景提供稳定中转与配套服务，适合需要高可用接口、便捷接入和持续交付支持的开发者与团队。可前往官网了解最新方案。 | [https://ai.xiaoye.io/](https://ai.xiaoye.io/) |

## 赞助支持

如果这个项目对你有帮助，欢迎赞助支持项目继续维护与更新。

![打赏码](docs/images/dashang.JPG)

## Star History

<a href="https://www.star-history.com/?repos=zc-zhangchen%2Fany-auto-register&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=zc-zhangchen/any-auto-register&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=zc-zhangchen/any-auto-register&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=zc-zhangchen/any-auto-register&type=date&legend=top-left" />
 </picture>
</a>

## License

MIT License — 仅供学习研究，禁止商业使用。
