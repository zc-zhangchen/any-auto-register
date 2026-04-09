"""Tmailor 临时邮箱服务 (tmailor.com)

基于 tmailor.com API 创建临时邮箱并轮询收件箱。
使用 curl_cffi 绕过 Cloudflare 保护。
环境变量 TMAILOR_API_KEY 可设置认证 token。
"""

import json
import os
import re
import time
import threading
from typing import Any, Optional

from curl_cffi import requests as cffi_requests

from .base_mailbox import BaseMailbox, MailboxAccount
from .proxy_utils import build_requests_proxy_config

BASE_URL = "https://tmailor.com"
API_URL = f"{BASE_URL}/api"

TMALLOR_API_KEY = os.getenv("TMAILOR_API_KEY", "").strip()

_BLOCKED_POOL_FILE = "tmailor_blocked_pool.json"
_blocked_pool_lock = threading.Lock()


def _load_blocked_pool() -> list[dict]:
    try:
        with open(_BLOCKED_POOL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_blocked_pool(pool: list[dict]) -> None:
    with _blocked_pool_lock:
        with open(_BLOCKED_POOL_FILE, "w", encoding="utf-8") as f:
            json.dump(pool, f, ensure_ascii=False, indent=2)


def add_to_blocked_pool(email: str, reason: str = "add_phone", extra: dict = None) -> None:
    pool = _load_blocked_pool()
    for item in pool:
        if item.get("email", "").lower() == email.lower():
            return
    pool.append({
        "email": email,
        "reason": reason,
        "blocked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "extra": extra or {},
    })
    _save_blocked_pool(pool)


def remove_from_blocked_pool(email: str) -> bool:
    pool = _load_blocked_pool()
    original_len = len(pool)
    pool = [item for item in pool if item.get("email", "").lower() != email.lower()]
    if len(pool) < original_len:
        _save_blocked_pool(pool)
        return True
    return False


def get_blocked_pool() -> list[dict]:
    return _load_blocked_pool()


def clear_blocked_pool() -> None:
    _save_blocked_pool([])


class TmailorMailbox(BaseMailbox):
    """Tmailor 临时邮箱服务"""

    def __init__(self, proxy: str = None):
        self.base_url = BASE_URL
        self.api_url = API_URL
        self.proxy_url = proxy
        self._session: cffi_requests.Session | None = None
        self._impersonate = "chrome136"

    def _get_session(self) -> cffi_requests.Session:
        if self._session is None:
            proxies = None
            if self.proxy_url:
                proxies = {"http": self.proxy_url, "https": self.proxy_url}
            self._session = cffi_requests.Session(
                impersonate=self._impersonate,
                proxies=proxies,
                timeout=20,
            )
            self._session.headers.update({
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            })
            if TMALLOR_API_KEY:
                self._session.headers["Authorization"] = f"Bearer {TMALLOR_API_KEY}"
        return self._session

    def _create_mailbox(self) -> dict:
        session = self._get_session()
        session.get(self.base_url + "/", timeout=20)
        r = session.post(self.api_url, json={
            "action": "newemail",
            "fbToken": None,
            "curentToken": None,
        }, timeout=20)
        data = r.json()
        if data.get("msg") not in ("ok", "errorcaptcha"):
            raise RuntimeError(f"Tmailor 创建邮箱失败: {data}")
        if data.get("msg") == "errorcaptcha" or not data.get("email"):
            raise RuntimeError(f"Tmailor Cloudflare 验证失败 (errorcaptcha)，请稍后重试: {data}")
        return {
            "email": data["email"],
            "token": data["accesstoken"],
        }

    def _read_mail_detail(self, token: str, message: dict) -> dict | None:
        session = self._get_session()
        r = session.post(self.api_url, json={
            "action": "read",
            "accesstoken": token,
            "curentToken": token,
            "fbToken": None,
            "email_code": message.get("id"),
            "email_token": message.get("email_id"),
        }, timeout=20)
        data = r.json()
        return data.get("data") if data.get("msg") == "ok" else None

    def _list_inbox(self, token: str, list_id: str = None) -> tuple[str | None, list[dict]]:
        session = self._get_session()
        headers = {"listid": list_id} if list_id else {}
        r = session.post(self.api_url, json={
            "action": "listinbox",
            "accesstoken": token,
            "curentToken": token,
            "fbToken": None,
        }, headers=headers, timeout=20)
        data = r.json()
        if data.get("msg") == "ok":
            new_list_id = data.get("code") or list_id
            messages = data.get("data") or {}
            return new_list_id, list(messages.values())
        return list_id, []

    def get_email(self) -> MailboxAccount:
        try:
            box = self._create_mailbox()
        except RuntimeError as e:
            if "errorcaptcha" in str(e) or "Cloudflare" in str(e):
                self._log(f"[Tmailor] Cloudflare 验证中，等待 10 秒后重试...")
                time.sleep(10)
                self._session = None
                box = self._create_mailbox()
            else:
                raise

        email = box["email"]
        token = box["token"]

        blocked = [item.get("email", "").lower() for item in get_blocked_pool()]
        if email.lower() in blocked:
            self._log(f"[Tmailor] 邮箱 {email} 在封禁池中，重新创建")
            return self.get_email()

        self._log(f"[Tmailor] 生成邮箱: {email}")
        return MailboxAccount(
            email=email,
            account_id=token,
            extra={
                "provider": "tmailor",
                "token": token,
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        token = account.account_id
        if not token:
            return set()
        try:
            _, messages = self._list_inbox(token)
            return {str(msg.get("id") or "") for msg in messages if msg.get("id")}
        except Exception:
            return set()

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        token = account.account_id
        if not token:
            raise RuntimeError("Tmailor 缺少 token")

        seen = {str(mid) for mid in (before_ids or set())}
        list_id = None
        end = time.time() + timeout

        while time.time() < end:
            self._checkpoint()
            list_id, messages = self._list_inbox(token, list_id)

            for msg in messages:
                mid = str(msg.get("id") or "")
                if mid in seen:
                    continue
                seen.add(mid)

                detail = self._read_mail_detail(token, msg) or {}
                text = " ".join(str(x) for x in [
                    msg.get("subject"), msg.get("text"), msg.get("body"),
                    detail.get("subject"), detail.get("text"), detail.get("body")
                ] if x)

                if keyword and keyword.lower() not in text.lower():
                    continue

                m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
                if not m:
                    continue

                code = m.group(1)
                subject = (detail.get("subject") or msg.get("subject") or "").strip()

                if subject.lower() != f"your chatgpt code is {code}".lower():
                    continue

                self._log(f"[Tmailor] 收到验证码: {code}")
                return code

            remaining = end - time.time()
            if remaining <= 0:
                break
            self._sleep_with_checkpoint(min(5, remaining))

        self._checkpoint()
        raise TimeoutError(f"[Tmailor] 等待验证码超时 ({timeout}s)")
