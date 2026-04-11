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

def _get_api_key() -> str:
    try:
        from .config_store import config_store
        val = config_store.get("tmailor_api_key", "")
        if val:
            return val.strip()
    except Exception:
        pass
    return os.getenv("TMAILOR_API_KEY", "").strip()


TMALLOR_API_KEY = ""  # 运行时通过 _get_api_key() 动态读取

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
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            })
            api_key = _get_api_key()
            if api_key:
                self._session.headers["Authorization"] = f"Bearer {api_key}"
            # 关键: 先访问首页,设置 cookies (包括 Cloudflare cf_clearance)
            try:
                self._session.get(self.base_url + "/", timeout=20)
                self._log("[Tmailor] 已访问首页,设置 session cookies")
            except Exception as e:
                self._log(f"[Tmailor] 访问首页失败: {e}")
        return self._session

    def _create_mailbox(self) -> dict:
        session = self._get_session()
        # 注意: _get_session() 已经访问过首页了,不需要重复访问
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
        payload = {
            "action": "listinbox",
            "accesstoken": token,
            "curentToken": token,
            "fbToken": None,
        }
        self._log(f"[Tmailor] 请求参数: action=listinbox, has_listid={bool(list_id)}")
        r = session.post(self.api_url, json=payload, headers=headers, timeout=20)
        data = r.json()
        self._log(f"[Tmailor] API 完整响应: {data}")
        if data.get("msg") == "ok":
            new_list_id = data.get("code") or list_id
            messages = data.get("data") or {}
            if messages:
                self._log(f"[Tmailor] 邮件 IDs: {list(messages.keys())[:5]}...")
            return new_list_id, list(messages.values())
        return list_id, []

    def _is_openai_mail(self, msg: dict, detail: dict = None) -> bool:
        """判断是否为 OpenAI/ChatGPT 邮件"""
        subject = str((detail or {}).get("subject") or msg.get("subject") or "").lower()
        text = str((detail or {}).get("text") or msg.get("text") or "").lower()
        body = str((detail or {}).get("body") or msg.get("body") or "").lower()
        from_addr = str(msg.get("from") or "").lower()

        combined = f"{subject} {text} {body} {from_addr}"
        return (
            "openai" in from_addr or "openai" in combined or
            "chatgpt" in subject or "verify" in subject or
            "verification" in subject or "code" in subject
        )

    def _extract_code_from_mail(self, msg: dict, detail: dict = None, code_pattern: str = None) -> str | None:
        """从邮件中提取验证码"""
        for key in ("verification_code", "code", "otp"):
            value = str((detail or {}).get(key) or msg.get(key) or "").strip()
            if value and re.match(r"^\d{6}$", value):
                return value

        for text in [
            str((detail or {}).get(k) or msg.get(k) or "")
            for k in ("subject", "text", "body")
        ]:
            if not text:
                continue
            m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
            if m:
                return m.group(1)

        return None

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
        self._log(f"[Tmailor] Token: {token}")
        self._log(f"[Tmailor] 访问方式: 打开 {self.base_url} 输入上面的 token")
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
        otp_sent_at: float = None,
        exclude_codes: set = None,
        target_email: str = None,
        **kwargs,
    ) -> str:
        token = account.account_id
        self._log(f"[Tmailor] wait_for_code 开始: email={account.email}, has_token={bool(token)}, token_len={len(str(token or ''))}")
        if not token:
            raise RuntimeError("Tmailor 缺少 token")

        seen = {str(mid) for mid in (before_ids or set())}
        excluded = set(exclude_codes or set())
        list_id = None
        end = time.time() + timeout

        while time.time() < end:
            self._checkpoint()
            list_id, messages = self._list_inbox(token, list_id)

            self._log(f"[Tmailor] 轮询邮件: list_id={list_id}, 收到 {len(messages)} 封邮件")

            for msg in messages:
                mid = str(msg.get("id") or "")
                if mid in seen:
                    continue
                seen.add(mid)

                subject = msg.get("subject") or ""
                self._log(f"[Tmailor] 检查邮件: id={mid[:20]}..., subject={subject}")

                # 读取详情
                detail = self._read_mail_detail(token, msg) or {}

                # 判断是否为 OpenAI 邮件
                is_openai = self._is_openai_mail(msg, detail)
                self._log(f"[Tmailor] 是否为 OpenAI 邮件: {is_openai}")
                if not is_openai:
                    continue

                # 提取验证码
                code = self._extract_code_from_mail(msg, detail, code_pattern)
                self._log(f"[Tmailor] 提取的验证码: {code}")
                if not code:
                    continue

                if code in excluded:
                    self._log(f"[Tmailor] 跳过已使用的验证码: {code}")
                    continue

                self._log(f"[Tmailor] 收到验证码: {code}")
                return code

            remaining = end - time.time()
            if remaining <= 0:
                break
            self._sleep_with_checkpoint(min(5, remaining))

        self._checkpoint()
        raise TimeoutError(f"[Tmailor] 等待验证码超时 ({timeout}s)")
