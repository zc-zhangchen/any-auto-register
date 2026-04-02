"""account_manager - 多平台账号管理后台"""
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from core.db import init_db
from core.registry import load_all
from api.accounts import router as accounts_router
from api.tasks import router as tasks_router
from api.platforms import router as platforms_router
from api.proxies import router as proxies_router
from api.config import router as config_router
from api.actions import router as actions_router
from api.integrations import router as integrations_router

EXPECTED_VENV_DIR = os.getenv("APP_VENV_DIR", ".venv")


def _expected_virtual_env_path() -> str:
    """AI by zb: 返回项目期望使用的虚拟环境绝对路径。"""
    if os.path.isabs(EXPECTED_VENV_DIR):
        return os.path.normpath(EXPECTED_VENV_DIR)
    return os.path.normpath(os.path.join(os.path.dirname(__file__), EXPECTED_VENV_DIR))


def _detect_virtual_env() -> tuple[str, str]:
    """AI by zb: 检测当前 Python 所在的虚拟环境名称与路径。"""
    virtual_env = os.getenv("VIRTUAL_ENV")
    if virtual_env:
        normalized = os.path.normpath(virtual_env)
        return os.path.basename(normalized), normalized

    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    if sys.prefix != base_prefix:
        normalized = os.path.normpath(sys.prefix)
        return os.path.basename(normalized), normalized
    return "", ""


def _is_expected_virtual_env(current_path: str) -> bool:
    """AI by zb: 判断当前虚拟环境是否为项目约定的环境路径。"""
    if not current_path:
        return False
    expected = os.path.normcase(os.path.abspath(_expected_virtual_env_path()))
    current = os.path.normcase(os.path.abspath(current_path))
    return current == expected


def _print_runtime_info() -> None:
    expected_env_path = _expected_virtual_env_path()
    current_env, current_env_path = _detect_virtual_env()
    print(f"[Runtime] Python: {sys.executable}")
    print(f"[Runtime] Virtual Env: {current_env_path or '未检测到'}")
    if current_env and not _is_expected_virtual_env(current_env_path):
        print(
            f"[WARN] 当前虚拟环境为 '{current_env}'，推荐使用 '{expected_env_path}' 启动，"
            "否则 Turnstile Solver 可能因依赖缺失而无法启动。"
        )
    elif not current_env_path:
        print(
            f"[WARN] 未检测到项目虚拟环境，推荐使用 '{expected_env_path}' 启动，"
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
