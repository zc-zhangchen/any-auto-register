# 使用 ClawCloud 部署 any-auto-register

本文档包含两部分：
- 如何用 GitHub Actions 自动构建并推送镜像
- 如何在 ClawCloud Run 上部署并持久化数据

## 1. 准备条件

- 已有 GitHub 仓库（本项目）
- 已开通 ClawCloud Run
- Docker 镜像仓库可用（推荐 GHCR）

## 2. 启用 GitHub Actions 构建镜像

本仓库已提供工作流文件：
- `.github/workflows/docker-image.yml`

它会在以下场景执行：
- 推送到 `main` 或 `master`
- 打 `v*` 标签（如 `v1.0.0`）
- 手动触发（`workflow_dispatch`）

默认推送到 GHCR，镜像地址格式：
- `ghcr.io/<你的GitHub用户名或组织>/any-auto-register`

### 2.1 仓库设置

在 GitHub 仓库中确认：
- `Settings -> Actions -> General -> Workflow permissions` 允许 `Read and write permissions`
- 仓库 Actions 可运行

### 2.2 推送一次触发构建

```bash
git add .github/workflows/docker-image.yml docs/CLAWCLOUD_DEPLOY.md
git commit -m "chore: add clawcloud deployment guide and docker image workflow"
git push
```

构建成功后，在 `Packages` 或 Actions 日志中可以看到镜像标签，例如：
- `latest`
- `main`
- `sha-<commit-short-sha>`
- `v1.0.0`（仅 tag 发布时）

## 3. 在 ClawCloud Run 创建应用

### 3.1 新建应用

- 进入 ClawCloud Run 控制台
- 选择 `App Launchpad` 创建应用
- Deployment source 选择容器镜像（Image）
- 填入镜像地址：
  - `ghcr.io/<你的GitHub用户名或组织>/any-auto-register:latest`

说明：
- 如果 GHCR 镜像是私有，需要在 ClawCloud 配置镜像仓库凭据
- 建议先将镜像设为 public，部署更简单

### 3.2 实例与端口

- Deploy mode：`Fixed`
- Replicas：`1`
- Exposed port：`8000`（HTTP 对外）

可选端口：
- `8889` 是 solver 端口，通常不建议公网暴露

## 4. 持久化存储（关键）

在 ClawCloud 的 `Persistent Storage` / `Local Storage` 中添加挂载：

- 挂载 `/<storage>/runtime` 到容器路径 `/runtime`（必选）
- 挂载 `/<storage>/ext_targets` 到容器路径 `/_ext_targets`（可选）
- 挂载 `/<storage>/external_logs` 到容器路径 `/app/services/external_logs`（可选）

为什么必须挂载 `/runtime`：
- `docker/entrypoint.sh` 会在 `/runtime` 下创建 `account_manager.db`、日志及缓存文件
- 不挂载会导致重建容器后数据丢失

## 5. 环境变量配置

在 ClawCloud 应用环境变量中设置：

- `HOST=0.0.0.0`
- `PORT=8000`
- `APP_RELOAD=0`
- `APP_CONDA_ENV=docker`
- `APP_RUNTIME_DIR=/runtime`
- `APP_ENABLE_SOLVER=1`
- `SOLVER_PORT=8889`
- `SOLVER_BIND_HOST=0.0.0.0`
- `LOCAL_SOLVER_URL=http://127.0.0.1:8889`
- `SOLVER_BROWSER_TYPE=camoufox`

业务相关可按需增加：
- `OPENAI_*`
- `SMSTOME_COOKIE`
- 其他第三方服务密钥

## 6. 启动后验证

部署完成后检查：

- 打开首页：`http(s)://<你的域名>/`
- 接口检查：`http(s)://<你的域名>/api/solver/status`

预期返回示例：

```json
{"running": true}
```

如果你禁用了 solver（`APP_ENABLE_SOLVER=0`），返回可能是：

```json
{"running": false}
```

## 7. 升级流程

- 本地更新代码并 push 到 `main`
- GitHub Actions 自动构建并推送新镜像
- 在 ClawCloud 里重新部署最新 tag（或保持 `latest` 并重启）
- 因为 `/runtime` 已挂载，业务数据会保留

## 8. 常见问题

### 8.1 数据丢失

原因通常是没挂载 `/runtime`。  
处理：在 ClawCloud 补充持久化存储挂载到 `/runtime`，再重新部署。

### 8.2 容器启动后无法访问

检查：
- 端口是否暴露 `8000`
- `HOST` 是否为 `0.0.0.0`
- 应用日志是否有报错

### 8.3 使用 SQLite 的副本数建议

当前项目默认 SQLite，建议单副本运行（`Replicas=1`）。  
若需要多副本高可用，建议改造为 PostgreSQL。

