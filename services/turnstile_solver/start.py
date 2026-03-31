"""启动本地 Turnstile Solver 服务"""
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

from api_solver import create_app, parse_args
import asyncio


def _prepend_env_path(name: str, value: str) -> None:
    current = os.getenv(name, "")
    parts = [p for p in current.split(":") if p]
    if value in parts:
        return
    os.environ[name] = ":".join([value, *parts]) if parts else value


def _prepare_camoufox_env(browser_type: str) -> None:
    if browser_type != "camoufox" or os.name == "nt":
        return
    try:
        from platformdirs import user_cache_dir
    except Exception:
        return

    camoufox_dir = Path(user_cache_dir("camoufox"))
    if camoufox_dir.is_dir():
        _prepend_env_path("LD_LIBRARY_PATH", str(camoufox_dir))

if __name__ == "__main__":
    args = parse_args()
    _prepare_camoufox_env(args.browser_type)
    app = create_app(
        headless=not args.no_headless,
        useragent=args.useragent,
        debug=args.debug,
        browser_type=args.browser_type,
        thread=args.thread,
        proxy_support=args.proxy,
        use_random_config=args.random,
        browser_name=args.browser,
        browser_version=args.version,
    )
    app.run(host=args.host, port=int(args.port))
