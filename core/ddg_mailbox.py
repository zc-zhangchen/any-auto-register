"""DuckDuckGo Email Protection 邮箱别名服务。

两段式架构：
  1. 生成邮箱：调用 DDG API → xxx@duck.com
  2. 收取验证码：邮件由 DDG 转发到 Cloudflare Worker → 程序通过 CF API 获取

支持多组 Key (Token + Cloudflare URL)，自动按日限额轮转。
后台线程定时拉取邮件到本地缓存，避免并发轮询打爆 Cloudflare Worker。
"""

import json
import re
import time
import threading
import logging
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

from .base_mailbox import BaseMailbox, MailboxAccount
from .proxy_utils import build_requests_proxy_config

logger = logging.getLogger(__name__)


def _parse_keys_config(raw: str | list) -> list[dict]:
    """
    解析 DDG 多 Key 配置。

    接受 JSON 数组字符串或 list，每项应包含：
      - ddg_token: DDG Bearer Token
      - mail_inbox_url: Cloudflare 邮箱收件 URL（带 JWT）
      - label: (可选) 标签
    """
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
        token = str(item.get("ddg_token") or "").strip()
        inbox_url = str(item.get("mail_inbox_url") or "").strip()
        if not token or not inbox_url:
            continue
        result.append(
            {
                "ddg_token": token,
                "mail_inbox_url": inbox_url,
                "label": str(item.get("label") or f"Key-{len(result)+1}").strip(),
            }
        )
    return result


def _parse_inbox_url(inbox_url: str) -> tuple[str, str]:
    """
    从 mailInboxUrl 中解析 base_url 和 JWT。

    例如: https://mail.example.com/?jwt=eyJ... → ("https://mail.example.com", "eyJ...")
    """
    parsed = urlparse(inbox_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    params = parse_qs(parsed.query)
    jwt = ""
    for key in ("jwt", "token", "auth"):
        values = params.get(key, [])
        if values:
            jwt = values[0]
            break

    if not jwt and parsed.fragment:
        fragment_params = parse_qs(parsed.fragment)
        for key in ("jwt", "token", "auth"):
            values = fragment_params.get(key, [])
            if values:
                jwt = values[0]
                break

    return base_url, jwt


# ─── 全局邮件缓存 ───────────────────────────────────────────────
class _DDGMailCache:
    """后台定时拉取所有 key 的邮件到本地缓存，所有实例共享读取。"""

    def __init__(self):
        self._cache: dict[str, list[dict]] = {}
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
            self._thread = threading.Thread(target=self._loop, daemon=True, name="ddg-mail-cache")
            self._thread.start()
            self._log(f"[DDG] 邮件缓存后台线程已启动，每 {self._interval}s 刷新一次")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def get_mails(self, inbox_url: str) -> list[dict]:
        with self._lock:
            return list(self._cache.get(inbox_url.rstrip("/"), []))

    def _log(self, msg: str):
        if self._log_fn:
            self._log_fn(msg)

    def _loop(self):
        while self._running:
            try:
                self._refresh_all()
            except Exception as e:
                self._log(f"[DDG] 邮件缓存刷新异常: {e}")
            for _ in range(int(self._interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _refresh_all(self):
        for key in self._keys:
            if not self._running:
                return
            inbox_url = key.get("mail_inbox_url", "").rstrip("/")
            if not inbox_url:
                continue
            base_url, jwt = _parse_inbox_url(inbox_url)
            if not jwt:
                continue
            self._fetch_one(inbox_url, base_url, jwt)

    def _fetch_one(self, inbox_url: str, base_url: str, jwt: str):
        import requests

        headers = {"Accept": "application/json", "Authorization": f"Bearer {jwt}"}
        try:
            resp = requests.get(
                f"{base_url}/api/mails",
                params={"limit": 50, "offset": 0},
                headers=headers,
                proxies=self._proxy,
                timeout=15,
            )
            if resp.status_code != 200:
                if resp.status_code == 401:
                    self._log("[DDG] 缓存: JWT 无效或已过期")
                return

            payload = resp.json()
            if isinstance(payload, list):
                mails = payload
            elif isinstance(payload, dict):
                mails = payload.get("results") or payload.get("mails") or payload.get("data") or []
            else:
                mails = []

            with self._lock:
                self._cache[inbox_url] = mails
        except Exception as e:
            error_str = str(e)
            is_transient = any(kw in error_str for kw in ("SSL", "UNEXPECTED_EOF", "ConnectionError", "ReadTimeout", "ConnectTimeout", "Max retries"))
            if is_transient:
                self._log(f"[DDG] 缓存: 获取邮件出错 (瞬时错误): {e}")
            else:
                self._log(f"[DDG] 缓存: 获取邮件出错: {e}")


_global_mail_cache = _DDGMailCache()


class DuckDuckGoMailbox(BaseMailbox):
    """DuckDuckGo Email Protection + Cloudflare Worker 两段式邮箱服务。"""

    DDG_API = "https://quack.duckduckgo.com/api/email/addresses"
    _alias_allocation_lock = threading.Lock()

    def __init__(
        self,
        keys_config: str | list = "[]",
        daily_limit: int = 50,
        proxy: str = None,
    ):
        self.keys = _parse_keys_config(keys_config)
        if not self.keys:
            raise RuntimeError(
                "DDG 邮箱服务未配置任何有效的 Key，"
                "请在设置中配置 ddg_keys_config（JSON 数组格式）"
            )
        self.proxy = build_requests_proxy_config(proxy)
        self.daily_limit = max(int(daily_limit or 50), 1)

        from .ddg_tracker import DdgUsageTracker
        self._tracker = DdgUsageTracker(daily_limit=self.daily_limit)

        # 注册到全局缓存（仅首次生效）
        _global_mail_cache.configure(
            keys=self.keys,
            proxy=self.proxy,
            interval=5,
            log_fn=lambda msg: self._log(msg),
        )
        _global_mail_cache.start()

    def _generate_alias(self, key_index: int) -> str:
        import requests

        token = self.keys[key_index]["ddg_token"]
        auth_header = token if token.startswith("Bearer ") else f"Bearer {token}"

        response = requests.post(
            self.DDG_API,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={},
            proxies=self.proxy,
            timeout=15,
        )

        if response.status_code not in (200, 201):
            raise RuntimeError(f"DDG API 返回错误: HTTP {response.status_code} - {response.text[:200]}")

        data = response.json()
        address = data.get("address", "")
        if not address:
            raise RuntimeError(f"DDG API 返回空地址: {data}")

        return f"{address}@duck.com"

    def get_email(self) -> MailboxAccount:
        with self._alias_allocation_lock:
            key_index = self._tracker.get_available_key_index(len(self.keys))
            key_config = self.keys[key_index]
            label = key_config.get("label", f"Key-{key_index}")

            self._log(f"[DDG] 使用 {label} (索引 {key_index})")

            email = self._generate_alias(key_index)
            self._tracker.record_usage(key_index, email)
            usage = self._tracker.get_daily_usage(key_index)

        self._log(f"[DDG] 生成邮箱别名: {email} (今日用量: {usage}/{self.daily_limit})")

        return MailboxAccount(
            email=email,
            account_id=email,
            extra={
                "provider": "ddg",
                "key_index": key_index,
                "key_label": label,
                "mail_inbox_url": key_config["mail_inbox_url"],
            },
        )

    def _fetch_mails(self, base_url: str, jwt: str, limit: int = 5) -> list[dict]:
        """优先从本地缓存读取，缓存未就绪时 fallback 到直接请求。"""
        # 构造与缓存一致的 key
        inbox_url = f"{base_url}/?jwt={jwt}".rstrip("/")
        cached = _global_mail_cache.get_mails(inbox_url)
        if cached is not None:
            return cached[:limit]

        # Fallback: 直接请求（仅缓存未初始化时触发）
        import requests
        headers = {"Accept": "application/json", "Authorization": f"Bearer {jwt}"}
        try:
            resp = requests.get(
                f"{base_url}/api/mails",
                params={"limit": limit, "offset": 0},
                headers=headers,
                proxies=self.proxy,
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            payload = resp.json()
            if isinstance(payload, list):
                return payload[:limit]
            if isinstance(payload, dict):
                return (payload.get("results") or payload.get("mails") or payload.get("data") or [])[:limit]
            return []
        except Exception as e:
            self._log(f"[DDG] 获取邮件列表出错: {e}")
            return []

    def _is_openai_mail(self, mail: dict) -> bool:
        raw = str(mail.get("raw") or "").lower()
        subject = str(mail.get("subject") or "").lower()
        sender_raw = mail.get("from", "")
        sender = str(sender_raw.get("address") if isinstance(sender_raw, dict) else sender_raw).lower()

        return (
            "openai" in sender or "openai" in raw or
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

        for text in [str(mail.get(k) or "") for k in ("raw", "subject", "text", "body", "html", "snippet", "content")]:
            if not text:
                continue
            decoded = self._decode_raw_content(text)
            code = self._safe_extract(decoded or text, code_pattern)
            if code:
                return code
        return None

    def _resolve_mail_id(self, mail: dict) -> str:
        for key in ("id", "message_id", "uid", "mail_id", "_id"):
            value = str(mail.get(key) or "").strip()
            if value:
                return value
        import hashlib
        return hashlib.sha1(json.dumps(mail, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def get_current_ids(self, account: MailboxAccount) -> set:
        extra = account.extra or {}
        inbox_url = extra.get("mail_inbox_url", "")
        if not inbox_url:
            return set()
        base_url, jwt = _parse_inbox_url(inbox_url)
        mails = self._fetch_mails(base_url, jwt, limit=10)
        return {self._resolve_mail_id(mail) for mail in mails}

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
        """从本地缓存轮询等待验证码（零网络请求）。"""
        extra = account.extra or {}
        inbox_url = extra.get("mail_inbox_url", "")
        if not inbox_url:
            raise RuntimeError("DDG 邮箱账户缺少 mail_inbox_url，无法获取验证码")

        # 统一 Key 格式，与后台缓存保持一致
        inbox_key = inbox_url.rstrip("/")

        # 注意：seen 集合必须独立，不能跨线程/跨实例共享
        # get_current_ids() 已经废弃，改用 otp_sent_at 时间戳过滤
        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {str(c).strip() for c in (kwargs.get("exclude_codes") or set()) if str(c or "").strip()}

        def poll_once() -> Optional[str]:
            mails = _global_mail_cache.get_mails(inbox_url)
            for mail in mails:
                mail_id = self._resolve_mail_id(mail)
                if mail_id in seen:
                    continue
                seen.add(mail_id)

                otp_sent_at = kwargs.get("otp_sent_at")
                if otp_sent_at:
                    created_at = mail.get("created_at") or mail.get("createdAt")
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
                    target_prefix = target_email.split("@")[0] if "@" in target_email else target_email
                    raw_lower = str(mail.get("raw") or "").lower()
                    source = str(mail.get("source") or "")

                    # 优先从 source 字段精确匹配 (=alias@duck.com)
                    source_match = re.search(r"=([a-z0-9]+-[a-z0-9]+-[a-z0-9]+)@duck\.com", source, re.IGNORECASE)
                    if source_match:
                        source_alias = source_match.group(1).lower()
                        if source_alias != target_prefix:
                            continue
                    else:
                        # Fallback: 用完整地址的单词边界匹配 raw
                        addr_pattern = rf"\b{re.escape(target_prefix)}@duck\.com\b"
                        if not re.search(addr_pattern, raw_lower):
                            continue

                code = self._extract_code_from_mail(mail, code_pattern)
                if code and code in exclude_codes:
                    continue
                if code:
                    self._log(f"[DDG] 成功获取验证码: {code}")
                    return code
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=2,
            poll_once=poll_once,
            timeout_message=f"[DDG] 验证码获取超时 ({timeout}s)，请检查 Cloudflare 邮箱配置",
        )
