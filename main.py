"""account_manager - 多平台账号管理后台"""
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from core.db import init_db
from core.registry import load_all
from api.accounts import router as accounts_router
from api.tasks import router as tasks_router
from api.platforms import router as platforms_router
from api.proxies import router as proxies_router
from api.config import router as config_router
from api.actions import router as actions_router
from api.integrations import router as integrations_router
from api.auth import router as auth_router
from api.outlook import router as outlook_router
from api.contribution import router as contribution_router

EXPECTED_CONDA_ENV = os.getenv("APP_CONDA_ENV", "any-auto-register")


def _detect_conda_env() -> str:
    conda_env = os.getenv("CONDA_DEFAULT_ENV")
    if conda_env:
        return conda_env

    prefix_parts = os.path.normpath(sys.prefix).split(os.sep)
    if "envs" in prefix_parts:
        idx = prefix_parts.index("envs")
        if idx + 1 < len(prefix_parts):
            return prefix_parts[idx + 1]
    return ""


def _print_runtime_info() -> None:
    current_env = _detect_conda_env()
    print(f"[Runtime] Python: {sys.executable}")
    print(f"[Runtime] Conda Env: {current_env or '未检测到'}")
    if EXPECTED_CONDA_ENV == "docker":
        return
    if current_env and current_env != EXPECTED_CONDA_ENV:
        print(
            f"[WARN] 当前环境为 '{current_env}'，推荐使用 '{EXPECTED_CONDA_ENV}' 启动，"
            "否则 Turnstile Solver 可能因依赖缺失而无法启动。"
        )
    elif not current_env:
        print(
            f"[WARN] 未检测到 conda 环境，推荐使用 '{EXPECTED_CONDA_ENV}' 启动，"
            "否则 Turnstile Solver 可能因依赖缺失而无法启动。"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _print_runtime_info()
    init_db()
    load_all()
    print("[OK] 数据库初始化完成")
    from core.registry import list_platforms
    print(f"[OK] 已加载平台: {[p['name'] for p in list_platforms()]}")
    from core.scheduler import scheduler
    scheduler.start()
    from services.solver_manager import start_async
    start_async()
    yield
    from core.scheduler import scheduler as _scheduler
    _scheduler.stop()
    from services.solver_manager import stop
    stop()


app = FastAPI(title="Account Manager", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/auth/") or not path.startswith("/api/"):
        return await call_next(request)
    from core.config_store import config_store as _cs
    if not _cs.get("auth_password_hash", ""):
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "未认证，请先登录"}, status_code=401)
    try:
        from api.auth import verify_token
        verify_token(auth_header[7:])
    except HTTPException as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(platforms_router, prefix="/api")
app.include_router(proxies_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(actions_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(outlook_router, prefix="/api")
app.include_router(contribution_router, prefix="/api")


@app.get("/api/solver/status")
def solver_status():
    from services.solver_manager import is_running
    return {"running": is_running()}


@app.post("/api/solver/restart")
def solver_restart():
    from services.solver_manager import stop, start_async
    stop()
    start_async()
    return {"message": "重启中"}


_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        return FileResponse(os.path.join(_static_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload_enabled = os.getenv("APP_RELOAD", "0").lower() in {"1", "true", "yes"}
    uvicorn.run("main:app", host=host, port=port, reload=reload_enabled)
