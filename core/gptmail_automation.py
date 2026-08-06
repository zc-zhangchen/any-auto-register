"""GPTMail 网页端自动化客户端。

不依赖 GPTMail API Key，而是复用网页端首页下发的 cookie 与 browser auth token
来创建临时邮箱并轮询收件箱。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

from curl_cffi import requests as cffi_requests
from curl_cffi.requests import Response, Session

from .proxy_utils import normalize_proxy_url

DEFAULT_GPTMAIL_BASE_URL = "https://mail.chatgpt.org.uk"
_REFRESH_BUFFER_SECONDS = 120


class _InboxSession:
    """维护 GPTMail 网页端 cookie + inbox token 生命周期。"""

    def __init__(self, api_base: str, proxy_url: str | None = None):
        self.api_base = (api_base or DEFAULT_GPTMAIL_BASE_URL).rstrip("/")
        self.proxy_url = normalize_proxy_url(proxy_url)
        self.session: Session | None = None
        self.token = ""
        self.email = ""
        self.expires_at = 0
        self._lock = threading.Lock()
        self._initialized = False

    def _base_headers(self, referer_email: str = "") -> dict[str, str]:
        referer_path = f"/{referer_email}" if referer_email else "/"
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": f"{self.api_base}{referer_path}",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    def _ensure_session(self) -> Session:
        if self.session is None:
            proxy_url = self.proxy_url or normalize_proxy_url(
                os.environ.get("HTTPS_PROXY")
                or os.environ.get("HTTP_PROXY")
                or os.environ.get("GLOBAL_PROXY")
            )
            proxies = (
                {"http": proxy_url, "https": proxy_url}
                if proxy_url
                else None
            )
            self.session = cffi_requests.Session(
                impersonate="chrome",
                proxies=proxies,
                timeout=15,
            )
        return self.session

    def _init_session(self) -> None:
        """预热首页，拿到 cookie 和初始 browser auth token。"""
        if self._initialized:
            return

        headers = self._base_headers()
        headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        headers["sec-fetch-dest"] = "document"
        headers["sec-fetch-mode"] = "navigate"
        headers["sec-fetch-site"] = "none"

        response = self._ensure_session().get(f"{self.api_base}/", headers=headers, timeout=15)
        response.raise_for_status()

        match = re.search(r"__BROWSER_AUTH\s*=\s*(\{[^;]+\})", response.text)
        if match:
            try:
                auth = json.loads(match.group(1))
            except (TypeError, ValueError, json.JSONDecodeError):
                auth = {}
            self._sync_auth({"auth": auth})

        self._initialized = True

    def _sync_auth(self, payload: dict[str, Any] | None) -> None:
        auth = payload.get("auth") if isinstance(payload, dict) else None
        if not isinstance(auth, dict):
            return
        self.token = str(auth.get("token") or "").strip()
        self.email = str(auth.get("email") or "").strip().lower()
        try:
            self.expires_at = int(auth.get("expires_at") or 0)
        except (TypeError, ValueError):
            self.expires_at = 0

    def _need_refresh(self, target_email: str = "") -> bool:
        if not self.token:
            return True
        if self.expires_at - int(time.time()) <= _REFRESH_BUFFER_SECONDS:
            return True
        if target_email and self.email != str(target_email).strip().lower():
            return True
        return False

    def _refresh_token(self, target_email: str = "") -> None:
        email_addr = str(target_email or self.email or "").strip().lower()
        if not email_addr:
            raise RuntimeError("GPTMail automation 缺少邮箱地址，无法刷新 inbox token")

        headers = self._base_headers(email_addr)
        headers["content-type"] = "application/json"
        if self.token:
            headers["X-Inbox-Token"] = self.token

        response = self._ensure_session().post(
            f"{self.api_base}/api/inbox-token",
            json={"email": email_addr},
            headers=headers,
            timeout=15,
        )
        data = response.json() if 200 <= response.status_code < 300 else None
        if not isinstance(data, dict) or not data.get("success") or not data.get("auth"):
            raise RuntimeError(f"GPTMail automation 刷新 inbox token 失败: HTTP {response.status_code}")
        self._sync_auth(data)

    def _ensure_token(self, target_email: str = "") -> None:
        with self._lock:
            self._init_session()
            if self._need_refresh(target_email):
                self._refresh_token(target_email)

    def auth_request(
        self,
        method: str,
        path: str,
        *,
        target_email: str = "",
        **kwargs: Any,
    ) -> Response:
        self._ensure_token(target_email)
        headers = kwargs.pop("headers", None) or self._base_headers(target_email)
        if self.token:
            headers["X-Inbox-Token"] = self.token

        response = self._ensure_session().request(
            method.upper(),
            f"{self.api_base}{path}",
            headers=headers,
            **kwargs,
        )

        if response.status_code in {401, 403}:
            with self._lock:
                self._initialized = False
                self._init_session()
                self._refresh_token(target_email)
            headers["X-Inbox-Token"] = self.token
            response = self._ensure_session().request(
                method.upper(),
                f"{self.api_base}{path}",
                headers=headers,
                **kwargs,
            )

        content_type = str(response.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            try:
                payload = response.json()
            except Exception:
                payload = None
            self._sync_auth(payload if isinstance(payload, dict) else None)
        return response

    def generate_email(self) -> str:
        with self._lock:
            self.reset()
            headers = self._base_headers()
            headers["content-type"] = "application/json"
            self._init_session()
            if self.token:
                headers["X-Inbox-Token"] = self.token
            response = self._ensure_session().post(
                f"{self.api_base}/api/generate-email",
                headers=headers,
                json={},
                timeout=15,
            )
            data = response.json()
            self._sync_auth(data if isinstance(data, dict) else None)

            payload = data.get("data") if isinstance(data, dict) else None
            email_addr = str((payload or {}).get("email") or "").strip().lower()
            if isinstance(data, dict) and data.get("success") and email_addr:
                self.email = email_addr
                return email_addr

        raise RuntimeError(f"GPTMail automation 生成邮箱失败: {data}")

    def get_emails(self, email_addr: str) -> list[dict[str, Any]]:
        response = self.auth_request(
            "GET",
            "/api/emails",
            target_email=email_addr,
            params={"email": email_addr},
            timeout=10,
        )
        data = response.json()
        if isinstance(data, dict) and data.get("success"):
            payload = data.get("data") or {}
            emails = payload.get("emails", [])
            return [item for item in emails if isinstance(item, dict)]
        return []

    def reset(self) -> None:
        if self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass
        self.session = None
        self.token = ""
        self.email = ""
        self.expires_at = 0
        self._initialized = False


class GPTMailAutomationClient:
    """GPTMail 网页端自动化入口。"""

    def __init__(
        self,
        *,
        api_base: str = DEFAULT_GPTMAIL_BASE_URL,
        proxy_url: str | None = None,
    ):
        self._session = _InboxSession(api_base=api_base, proxy_url=proxy_url)

    @property
    def token(self) -> str:
        return self._session.token

    def reset(self) -> None:
        self._session.reset()

    def generate_email(self) -> str:
        return self._session.generate_email()

    def get_emails(self, email_addr: str) -> list[dict[str, Any]]:
        return self._session.get_emails(email_addr)
