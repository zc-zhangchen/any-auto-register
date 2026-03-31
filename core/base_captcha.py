"""验证码解决器基类"""
import os
from abc import ABC, abstractmethod


class BaseCaptcha(ABC):
    @abstractmethod
    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        """返回 Turnstile token"""
        ...

    @abstractmethod
    def solve_image(self, image_b64: str) -> str:
        """返回图片验证码文字"""
        ...


class YesCaptcha(BaseCaptcha):
    def __init__(self, client_key: str):
        self.client_key = client_key
        self.api = "https://api.yescaptcha.com"

    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        import requests, time, urllib3
        urllib3.disable_warnings()
        r = requests.post(f"{self.api}/createTask", json={
            "clientKey": self.client_key,
            "task": {"type": "TurnstileTaskProxyless",
                     "websiteURL": page_url, "websiteKey": site_key}
        }, timeout=30, verify=False)
        task_id = r.json().get("taskId")
        if not task_id:
            raise RuntimeError(f"YesCaptcha 创建任务失败: {r.text}")
        for _ in range(60):
            time.sleep(3)
            d = requests.post(f"{self.api}/getTaskResult", json={
                "clientKey": self.client_key, "taskId": task_id
            }, timeout=30, verify=False).json()
            if d.get("status") == "ready":
                return d["solution"]["token"]
            if d.get("errorId", 0) != 0:
                raise RuntimeError(f"YesCaptcha 错误: {d}")
        raise TimeoutError("YesCaptcha Turnstile 超时")

    def solve_image(self, image_b64: str) -> str:
        raise NotImplementedError


class ManualCaptcha(BaseCaptcha):
    """人工打码，阻塞等待用户输入"""
    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        return input(f"请手动获取 Turnstile token ({page_url}): ").strip()

    def solve_image(self, image_b64: str) -> str:
        return input("请输入图片验证码: ").strip()


class LocalSolverCaptcha(BaseCaptcha):
    """调用本地 api_solver 服务解 Turnstile。"""

    def __init__(self, solver_url: str = ""):
        if not solver_url:
            solver_url = os.getenv("LOCAL_SOLVER_URL", "http://localhost:8889")
        self.solver_url = solver_url.rstrip("/")

    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        import requests, time
        # 提交任务
        r = requests.get(
            f"{self.solver_url}/turnstile",
            params={"url": page_url, "sitekey": site_key},
            timeout=15,
        )
        r.raise_for_status()
        task_id = r.json().get("taskId")
        if not task_id:
            raise RuntimeError(f"LocalSolver 未返回 taskId: {r.text}")
        # 轮询结果
        for _ in range(60):
            time.sleep(2)
            res = requests.get(
                f"{self.solver_url}/result",
                params={"id": task_id},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                status = data.get("status")
                if status == "ready":
                    token = data.get("solution", {}).get("token")
                    if token:
                        return token
                elif status == "CAPTCHA_FAIL":
                    raise RuntimeError("LocalSolver Turnstile 失败")
        raise TimeoutError("LocalSolver Turnstile 超时")

    def solve_image(self, image_b64: str) -> str:
        raise NotImplementedError

    @staticmethod
    def start_solver(headless: bool = True, browser_type: str = "chromium",
                     port: int = 8889) -> None:
        """在后台线程启动本地 solver 服务"""
        import subprocess, sys, os
        solver_path = os.path.join(
            os.path.dirname(__file__), "..", "services", "turnstile_solver", "start.py"
        )
        cmd = [
            sys.executable, solver_path,
            "--port", str(port),
            "--browser_type", browser_type,
        ]
        if not headless:
            cmd.append("--no-headless")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 等待服务启动
        import time, requests
        for _ in range(20):
            time.sleep(1)
            try:
                requests.get(f"http://localhost:{port}/", timeout=2)
                return
            except Exception:
                pass
        raise RuntimeError("LocalSolver 启动超时")
