"""Mail.tm 临时邮箱服务。

通过 Mail.tm API 创建/登录账号，后台线程定时拉取邮件到本地缓存。
配置格式 (JSON 数组):
  [{"address": "xxx@sharebot.net", "password": "xxx", "label": "Key-1"}]
"""

import json
import re
import time
import threading
import logging
from typing import Any, Optional

import requests

from .base_mailbox import BaseMailbox, MailboxAccount
from .proxy_utils import build_requests_proxy_config

logger = logging.getLogger(__name__)

API_BASE = "https://api.mail.tm"


def _parse_keys_config(raw: str | list) -> list[dict]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            items = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
    else:
        return []

    if not isinstance(items, list):
        return []

    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address") or "").strip()
        password = str(item.get("password") or "").strip()
        if not address or not password:
            continue
        result.append({
            "address": address,
            "password": password,
            "label": str(item.get("label") or f"Key-{len(result)+1}").strip(),
        })
    return result


# ─── 全局邮件缓存 ───────────────────────────────────────────────
class _MailTmCache:
    """后台定时拉取所有 Mail.tm 账号的邮件到本地缓存。"""

    def __init__(self):
        self._cache: dict[str, list[dict]] = {}
        self._tokens: dict[str, str] = {}
        self._account_ids: dict[str, str] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._keys: list[dict] = []
        self._proxy: dict | None = None
        self._interval = 5
        self._log_fn = None

    def configure(self, keys: list[dict], proxy: dict | None = None, interval: int = 5, log_fn=None):
        with self._lock:
            if not self._keys or self._keys != keys:
                self._keys = keys
                self._proxy = proxy
                self._interval = max(interval, 2)
            if log_fn and not self._log_fn:
                self._log_fn = log_fn

    def start(self):
        with self._lock:
            if self._running or not self._keys:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="mailtm-cache")
            self._thread.start()
            self._log(f"[Mail.tm] 邮件缓存后台线程已启动，每 {self._interval}s 刷新一次")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def get_mails(self, address: str) -> list[dict]:
        with self._lock:
            return list(self._cache.get(address, []))

    def _log(self, msg: str):
        if self._log_fn:
            self._log_fn(msg)

    def _login(self, address: str, password: str) -> str | None:
        """登录获取 JWT token。"""
        try:
            resp = requests.post(
                f"{API_BASE}/token",
                json={"address": address, "password": password},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                proxies=self._proxy,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token", "")
                account_id = data.get("id", "")
                if token:
                    with self._lock:
                        self._tokens[address] = token
                        if account_id:
                            self._account_ids[address] = account_id
                    return token
        except Exception as e:
            self._log(f"[Mail.tm] 登录失败 ({address}): {e}")
        return None

    def _loop(self):
        while self._running:
            try:
                self._refresh_all()
            except Exception as e:
                self._log(f"[Mail.tm] 邮件缓存刷新异常: {e}")
            for _ in range(int(self._interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _refresh_all(self):
        for key in self._keys:
            if not self._running:
                return
            address = key["address"]
            password = key["password"]

            token = self._tokens.get(address)
            if not token:
                token = self._login(address, password)
                if not token:
                    continue

            self._fetch_mails(address, token)

    def _fetch_mails(self, address: str, token: str):
        try:
            resp = requests.get(
                f"{API_BASE}/messages",
                params={"page": 1, "itemsPerPage": 50},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                proxies=self._proxy,
                timeout=15,
            )
            if resp.status_code == 401:
                self._log(f"[Mail.tm] Token 无效，尝试重新登录: {address}")
                new_token = self._login(address, self._keys[0]["password"] if self._keys else "")
                if new_token:
                    self._fetch_mails(address, new_token)
                return
            if resp.status_code != 200:
                return

            data = resp.json()
            members = data.get("hydra:member") or data.get("member") or data.get("messages") or []
            if not members:
                with self._lock:
                    self._cache[address] = []
                return

            # 获取每封邮件的详情
            mails = []
            for msg in members[:20]:
                msg_id = msg.get("id") or msg.get("@id", "").split("/")[-1]
                if not msg_id:
                    continue
                detail = self._fetch_message_detail(token, msg_id)
                if detail:
                    mails.append(detail)

            with self._lock:
                self._cache[address] = mails
        except Exception as e:
            error_str = str(e)
            is_transient = any(kw in error_str for kw in ("SSL", "UNEXPECTED_EOF", "ConnectionError", "ReadTimeout", "ConnectTimeout", "Max retries"))
            if is_transient:
                self._log(f"[Mail.tm] 缓存: 获取邮件出错 (瞬时错误): {e}")
            else:
                self._log(f"[Mail.tm] 缓存: 获取邮件出错: {e}")

    def _fetch_message_detail(self, token: str, msg_id: str) -> dict | None:
        try:
            resp = requests.get(
                f"{API_BASE}/messages/{msg_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                proxies=self._proxy,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None


_global_mail_cache = _MailTmCache()


class MailTmMailbox(BaseMailbox):
    """Mail.tm 临时邮箱。"""

    def __init__(
        self,
        keys_config: str | list = "[]",
        daily_limit: int = 50,
        proxy: str = None,
    ):
        self.keys = _parse_keys_config(keys_config)
        if not self.keys:
            raise RuntimeError(
                "Mail.tm 邮箱服务未配置任何有效的 Key，"
                "请在设置中配置 mailtm_keys_config（JSON 数组格式）"
            )
        self.proxy = build_requests_proxy_config(proxy)
        self.daily_limit = max(int(daily_limit or 50), 1)

        from .ddg_tracker import DdgUsageTracker
        self._tracker = DdgUsageTracker(daily_limit=self.daily_limit)

        _global_mail_cache.configure(
            keys=self.keys,
            proxy=self.proxy,
            interval=5,
            log_fn=lambda msg: self._log(msg),
        )
        _global_mail_cache.start()

    def get_email(self) -> MailboxAccount:
        key_index = self._tracker.get_available_key_index(len(self.keys))
        key_config = self.keys[key_index]
        label = key_config.get("label", f"Key-{key_index}")

        self._log(f"[Mail.tm] 使用 {label} (索引 {key_index}), 地址: {key_config['address']}")

        self._tracker.record_usage(key_index, key_config["address"])
        usage = self._tracker.get_daily_usage(key_index)

        self._log(f"[Mail.tm] 分配邮箱: {key_config['address']} (今日用量: {usage}/{self.daily_limit})")

        return MailboxAccount(
            email=key_config["address"],
            account_id=key_config["address"],
            extra={
                "provider": "mailtm",
                "key_index": key_index,
                "key_label": label,
                "address": key_config["address"],
                "password": key_config["password"],
            },
        )

    def _is_openai_mail(self, mail: dict) -> bool:
        raw = str(mail.get("text") or mail.get("html") or mail.get("intro") or "").lower()
        subject = str(mail.get("subject") or "").lower()
        from_addr = str((mail.get("from") or {}).get("address") or mail.get("from") or "").lower()

        return (
            "openai" in from_addr or "openai" in raw or
            "chatgpt" in subject or "verify" in subject or
            "verification" in subject or "code" in subject
        )

    def _extract_code_from_mail(self, mail: dict, code_pattern: str = None) -> Optional[str]:
        for key in ("verification_code", "code", "otp"):
            value = str(mail.get(key) or "").strip()
            if value:
                code = self._safe_extract(value, code_pattern)
                if code:
                    return code

        for text in [str(mail.get(k) or "") for k in ("text", "html", "intro", "subject")]:
            if not text:
                continue
            decoded = self._decode_raw_content(text)
            code = self._safe_extract(decoded or text, code_pattern)
            if code:
                return code
        return None

    def _resolve_mail_id(self, mail: dict) -> str:
        for key in ("id", "msgid", "@id", "message_id"):
            value = str(mail.get(key) or "").strip()
            if value:
                return value
        import hashlib
        return hashlib.sha1(json.dumps(mail, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def get_current_ids(self, account: MailboxAccount) -> set:
        extra = account.extra or {}
        address = extra.get("address", "")
        if not address:
            return set()
        mails = _global_mail_cache.get_mails(address)
        return {self._resolve_mail_id(m) for m in mails}

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        target_email: str = None,
        **kwargs,
    ) -> str:
        extra = account.extra or {}
        address = extra.get("address", "")
        if not address:
            raise RuntimeError("Mail.tm 邮箱账户缺少 address")

        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {str(c).strip() for c in (kwargs.get("exclude_codes") or set()) if str(c or "").strip()}

        def poll_once() -> Optional[str]:
            mails = _global_mail_cache.get_mails(address)
            for mail in mails:
                mail_id = self._resolve_mail_id(mail)
                if mail_id in seen:
                    continue
                seen.add(mail_id)

                otp_sent_at = kwargs.get("otp_sent_at")
                if otp_sent_at:
                    created_at = mail.get("createdAt") or mail.get("created_at")
                    if created_at:
                        try:
                            from datetime import datetime as dt, timezone
                            if isinstance(created_at, str):
                                parsed = dt.fromisoformat(created_at.replace("Z", "+00:00"))
                                if parsed.tzinfo is None:
                                    parsed = parsed.replace(tzinfo=timezone.utc)
                                mail_ts = parsed.timestamp()
                            else:
                                mail_ts = float(created_at)
                            if mail_ts < otp_sent_at - 10:
                                continue
                        except (ValueError, TypeError):
                            pass

                if not self._is_openai_mail(mail):
                    continue

                if target_email:
                    prefix = target_email.split("@")[0] if "@" in target_email else target_email
                    to_addr = str((mail.get("to") or {}).get("address") or mail.get("to") or "").lower()
                    if prefix not in to_addr and prefix not in str(mail.get("text") or mail.get("html") or "").lower():
                        continue

                code = self._extract_code_from_mail(mail, code_pattern)
                if code and code in exclude_codes:
                    continue
                if code:
                    self._log(f"[Mail.tm] 成功获取验证码: {code}")
                    return code
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=2,
            poll_once=poll_once,
            timeout_message=f"[Mail.tm] 验证码获取超时 ({timeout}s)，请检查 Mail.tm 账号配置",
        )
