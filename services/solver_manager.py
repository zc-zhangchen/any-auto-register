"""Turnstile Solver 进程管理 - 后端启动时自动拉起"""
import os
import socket
import subprocess
import sys
import threading
import time

import requests

REQUESTED_SOLVER_PORT = int(os.getenv("SOLVER_PORT", "8889"))
SOLVER_BROWSER_TYPE = os.getenv("SOLVER_BROWSER_TYPE", "chromium").strip() or "chromium"
_proc: subprocess.Popen = None
_log_file = None
_lock = threading.Lock()
_runtime_port: int | None = None


def _build_solver_url(port: int) -> str:
    return f"http://localhost:{port}"


def _probe_solver(port: int) -> bool:
    try:
        r = requests.get(f"{_build_solver_url(port)}/", timeout=2)
        if r.status_code >= 500:
            return False
        text = r.text or ""
        return "Turnstile Solver" in text
    except Exception:
        return False


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _pick_solver_port() -> int:
    if _probe_solver(REQUESTED_SOLVER_PORT) or _port_is_free(REQUESTED_SOLVER_PORT):
        return REQUESTED_SOLVER_PORT

    for port in range(REQUESTED_SOLVER_PORT + 1, REQUESTED_SOLVER_PORT + 21):
        if _port_is_free(port):
            print(
                f"[Solver] 端口 {REQUESTED_SOLVER_PORT} 已被其他进程占用，"
                f"自动切换到 {port}"
            )
            return port
    raise RuntimeError(
        f"未找到可用 Solver 端口，起始端口 {REQUESTED_SOLVER_PORT} 附近均不可用"
    )


def get_runtime_port() -> int:
    global _runtime_port
    if _runtime_port and _probe_solver(_runtime_port):
        return _runtime_port
    if _probe_solver(REQUESTED_SOLVER_PORT):
        _runtime_port = REQUESTED_SOLVER_PORT
        return _runtime_port
    return _runtime_port or REQUESTED_SOLVER_PORT


def get_runtime_url() -> str:
    return _build_solver_url(get_runtime_port())


def get_status() -> dict:
    port = get_runtime_port()
    running = _probe_solver(port)
    return {
        "running": running,
        "url": _build_solver_url(port),
        "port": port,
        "requested_port": REQUESTED_SOLVER_PORT,
        "browser_type": SOLVER_BROWSER_TYPE,
        "using_fallback_port": port != REQUESTED_SOLVER_PORT,
    }


def is_running() -> bool:
    return get_status()["running"]


def start():
    global _proc, _log_file, _runtime_port
    with _lock:
        status = get_status()
        if status["running"]:
            _runtime_port = status["port"]
            print(f"[Solver] 已在运行: {status['url']}")
            return

        solver_port = _pick_solver_port()
        _runtime_port = solver_port
        solver_script = os.path.join(
            os.path.dirname(__file__), "turnstile_solver", "start.py"
        )
        log_path = os.path.join(
            os.path.dirname(__file__), "turnstile_solver", "solver.log"
        )
        _log_file = open(log_path, "a", encoding="utf-8")
        _proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                solver_script,
                "--browser_type",
                SOLVER_BROWSER_TYPE,
                "--port",
                str(solver_port),
            ],
            stdout=_log_file,
            stderr=subprocess.STDOUT,
        )
        # 等待服务就绪（最多30s）
        for _ in range(30):
            time.sleep(1)
            if _probe_solver(solver_port):
                print(
                    f"[Solver] 已启动 PID={_proc.pid} URL={_build_solver_url(solver_port)} "
                    f"BROWSER={SOLVER_BROWSER_TYPE}"
                )
                return
            if _proc.poll() is not None:
                print(f"[Solver] 启动失败，退出码={_proc.returncode}，日志: {log_path}")
                _proc = None
                _runtime_port = None
                if _log_file:
                    _log_file.close()
                    _log_file = None
                return
        print(f"[Solver] 启动超时，日志: {log_path}")


def stop():
    global _proc, _log_file, _runtime_port
    with _lock:
        if _proc and _proc.poll() is None:
            _proc.terminate()
            _proc.wait(timeout=5)
            print("[Solver] 已停止")
        _proc = None
        _runtime_port = None
        if _log_file:
            _log_file.close()
            _log_file = None


def start_async():
    """在后台线程启动，不阻塞主进程"""
    t = threading.Thread(target=start, daemon=True)
    t.start()
