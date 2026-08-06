from __future__ import annotations

"""邮箱池基类 - 抽象临时邮箱/收件服务"""

import json
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .proxy_utils import build_requests_proxy_config


@dataclass
class MailboxAccount:
    email: str
    account_id: str = ""
    extra: dict = None  # 平台额外信息


class BaseMailbox(ABC):
    def _log(self, message: str) -> None:
        log_fn = getattr(self, "_log_fn", None)
        if callable(log_fn):
            log_fn(message)

    def _checkpoint(self, *, consume_skip: bool = True) -> None:
        task_control = getattr(self, "_task_control", None)
        if task_control is None:
            return
        task_control.checkpoint(
            consume_skip=consume_skip,
            attempt_id=getattr(self, "_task_attempt_token", None),
        )

    def _sleep_with_checkpoint(self, seconds: float) -> None:
        remaining = max(float(seconds or 0), 0.0)
        while remaining > 0:
            self._checkpoint()
            chunk = min(0.25, remaining)
            time.sleep(chunk)
            remaining -= chunk

    def _run_polling_wait(
        self,
        *,
        timeout: int,
        poll_interval: float,
        poll_once: Callable[[], Optional[str]],
        timeout_message: str | None = None,
    ) -> str:
        timeout_seconds = max(int(timeout or 0), 1)
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            self._checkpoint()
            code = poll_once()
            if code:
                return code

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._sleep_with_checkpoint(min(float(poll_interval), remaining))

        self._checkpoint()
        raise TimeoutError(timeout_message or f"等待验证码超时 ({timeout_seconds}s)")

    @abstractmethod
    def get_email(self) -> MailboxAccount:
        """获取一个可用邮箱"""
        ...

    @abstractmethod
    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        """等待并返回验证码，code_pattern 为自定义正则（默认匹配6位数字）"""
        ...

    def _safe_extract(self, text: str, pattern: str = None) -> Optional[str]:
        """通用验证码提取逻辑：若有捕获组则返回 group(1)，否则返回 group(0)"""
        import re

        text = str(text or "")
        if not text:
            return None

        patterns = []
        if pattern:
            patterns.append(pattern)

        # 先匹配带明显语义的验证码，避免误提取 MIME boundary、时间戳等 6 位数字。
        patterns.extend(
            [
                r"(?is)(?:verification\s+code|one[-\s]*time\s+(?:password|code)|security\s+code|login\s+code|验证码|校验码|动态码|認證碼|驗證碼)[^0-9]{0,30}(\d{6})",
                r"(?is)\bcode\b[^0-9]{0,12}(\d{6})",
                r"(?<!#)(?<!\d)(\d{6})(?!\d)",
            ]
        )

        for regex in patterns:
            m = re.search(regex, text)
            if m:
                # 兼容逻辑：若 pattern 中有捕获组则取 group(1)，否则取 group(0)
                return m.group(1) if m.groups() else m.group(0)
        return None

    def _decode_raw_content(self, raw: str) -> str:
        """解析邮件原始文本 (借鉴自 Fugle)，处理 Quoted-Printable 和 HTML 实体"""
        import html
        import quopri
        import re

        text = str(raw or "")
        if not text:
            return ""
        # 简单切分 Header 和 Body
        if "\r\n\r\n" in text:
            text = text.split("\r\n\r\n", 1)[1]
        elif "\n\n" in text:
            text = text.split("\n\n", 1)[1]
        try:
            # 处理 Quoted-Printable
            decoded_bytes = quopri.decodestring(text)
            text = decoded_bytes.decode("utf-8", errors="ignore")
        except Exception:
            pass
        # 清除 HTML 标签并反转义
        text = html.unescape(text)
        text = re.sub(r"(?im)^content-(?:type|transfer-encoding):.*$", " ", text)
        text = re.sub(r"(?im)^--+[_=\w.-]+$", " ", text)
        text = re.sub(r"(?i)----=_part_[\w.]+", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @abstractmethod
    def get_current_ids(self, account: MailboxAccount) -> set:
        """返回当前邮件 ID 集合（用于过滤旧邮件）"""
        ...
    def _yyds_safe_extract(self, text: str, pattern: str = None) -> Optional[str]:
        """通用验证码提取逻辑：若有捕获组则返回 group(1)，否则返回 group(0)"""
        import re

        text = str(text or "")
        if not text:
            return None

        # [修复点 1]：优先过滤掉所有 URL 链接，直接从根源防止提取到追踪链接（如 SendGrid）里的随机数字
        text = re.sub(r"https?://\S+", "", text)

        patterns = []
        if pattern:
            # [修复点 2]：如果外部传入了纯 \d{6} 的粗糙正则，自动为其加上字母数字边界
            if pattern in (r"\d{6}", r"(\d{6})"):
                patterns.append(r"(?<![a-zA-Z0-9])(\d{6})(?![a-zA-Z0-9])")
            else:
                patterns.append(pattern)

        # 先匹配带明显语义的验证码，避免误提取 MIME boundary、时间戳等 6 位数字。
        patterns.extend(
            [
                r"(?is)(?:verification\s+code|one[-\s]*time\s+(?:password|code)|security\s+code|login\s+code|验证码|校验码|动态码|認證碼|驗證碼)[^0-9]{0,30}(\d{6})",
                r"(?is)\bcode\b[^0-9]{0,12}(\d{6})",
                # [修复点 3]：修改兜底正则，严格要求 6 位数字前后不能有字母或数字（防止匹配 u20216706）
                r"(?<![a-zA-Z0-9])(\d{6})(?![a-zA-Z0-9])",
            ]
        )

        for regex in patterns:
            m = re.search(regex, text)
            if m:
                # 兼容逻辑：若 pattern 中有捕获组则取 group(1)，否则取 group(0)
                return m.group(1) if m.groups() else m.group(0)
        return None

    def _yyds_decode_raw_content(self, raw: str) -> str:
        """解析邮件原始文本 (借鉴自 Fugle)，处理 Quoted-Printable 和 HTML 实体"""
        import html
        import quopri
        import re

        text = str(raw or "")
        if not text:
            return ""
            
        # [修复点 4]：只有在明确包含常见邮件 Header 时，才进行 \r\n\r\n 切分。
        # 否则会误删 MaliAPI 等直接返回的已解析 JSON 正文内容（遇到普通的正文换行就错误截断了）
        if re.search(r"(?im)^(?:Return-Path|Received|Date|From|To|Subject|Content-Type):", text):
            if "\r\n\r\n" in text:
                text = text.split("\r\n\r\n", 1)[1]
            elif "\n\n" in text:
                text = text.split("\n\n", 1)[1]
                
        try:
            # 处理 Quoted-Printable
            decoded_bytes = quopri.decodestring(text)
            text = decoded_bytes.decode("utf-8", errors="ignore")
        except Exception:
            pass
        # 清除 HTML 标签并反转义
        text = html.unescape(text)
        text = re.sub(r"(?im)^content-(?:type|transfer-encoding):.*$", " ", text)
        text = re.sub(r"(?im)^--+[_=\w.-]+$", " ", text)
        text = re.sub(r"(?i)----=_part_[\w.]+", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

def create_mailbox(
    provider: str, extra: dict = None, proxy: str = None
) -> "BaseMailbox":
    """工厂方法：根据 provider 创建对应的 mailbox 实例"""
    extra = extra or {}
    if provider == "tempmail_lol":
        return TempMailLolMailbox(proxy=proxy)
    elif provider == "skymail":
        return SkyMailMailbox(
            api_base=extra.get("skymail_api_base", "https://api.skymail.ink"),
            auth_token=extra.get("skymail_token", ""),
            domain=extra.get("skymail_domain", ""),
            proxy=proxy,
        )
    elif provider == "cloudmail":
        timeout_raw = extra.get("cloudmail_timeout", extra.get("timeout", 30))
        try:
            timeout_value = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_value = 30
        return CloudMailMailbox(
            api_base=extra.get("cloudmail_api_base")
            or extra.get("base_url")
            or "",
            admin_email=extra.get("cloudmail_admin_email")
            or extra.get("admin_email")
            or "",
            admin_password=extra.get("cloudmail_admin_password")
            or extra.get("admin_password")
            or extra.get("api_key")
            or "",
            domain=extra.get("cloudmail_domain") or extra.get("domain") or "",
            subdomain=extra.get("cloudmail_subdomain")
            or extra.get("subdomain")
            or "",
            timeout=timeout_value,
            proxy=proxy,
        )
    elif provider == "duckmail":
        return DuckMailMailbox(
            api_url=(extra.get("duckmail_api_url") or "https://www.duckmail.sbs"),
            provider_url=(
                extra.get("duckmail_provider_url") or "https://api.duckmail.sbs"
            ),
            bearer=(extra.get("duckmail_bearer") or "kevin273945"),
            domain=extra.get("duckmail_domain", ""),
            api_key=extra.get("duckmail_api_key", ""),
            proxy=proxy,
        )
    elif provider == "freemail":
        return FreemailMailbox(
            api_url=extra.get("freemail_api_url", ""),
            admin_token=extra.get("freemail_admin_token", ""),
            username=extra.get("freemail_username", ""),
            password=extra.get("freemail_password", ""),
            domain=extra.get("freemail_domain", ""),
            proxy=proxy,
        )
    elif provider == "moemail":
        return MoeMailMailbox(
            api_url=extra.get("moemail_api_url", "https://sall.cc"),
            api_key=extra.get("moemail_api_key", ""),
            proxy=proxy,
        )
    elif provider == "maliapi":
        return MaliAPIMailbox(
            api_url=extra.get("maliapi_base_url", "https://maliapi.215.im/v1"),
            api_key=extra.get("maliapi_api_key", ""),
            domain=extra.get("maliapi_domain", ""),
            auto_domain_strategy=extra.get("maliapi_auto_domain_strategy", ""),
            proxy=proxy,
        )
    elif provider == "gptmail":
        return GPTMailMailbox(
            api_url=extra.get("gptmail_base_url", "https://mail.chatgpt.org.uk"),
            api_key=extra.get("gptmail_api_key", ""),
            domain=extra.get("gptmail_domain", ""),
            mode=extra.get("gptmail_mode", "api"),
            proxy=proxy,
        )
    elif provider == "applemail":
        return AppleMailMailbox(
            api_url=extra.get("applemail_base_url", "https://www.appleemail.top"),
            pool_file=extra.get("applemail_pool_file", ""),
            pool_dir=extra.get("applemail_pool_dir", "mail"),
            mailboxes=extra.get("applemail_mailboxes", "INBOX,Junk"),
            proxy=proxy,
        )
    elif provider == "opentrashmail":
        return OpenTrashMailMailbox(
            api_url=extra.get("opentrashmail_api_url", ""),
            domain=extra.get("opentrashmail_domain", ""),
            password=extra.get("opentrashmail_password", ""),
            proxy=proxy,
        )
    elif provider == "cfrouting":
        return CFRoutingMailbox(
            domain=extra.get("cfrouting_domain", ""),
            imap_server=extra.get("cfrouting_imap_server", ""),
            imap_port=extra.get("cfrouting_imap_port", 993),
            username=extra.get("cfrouting_username", ""),
            password=extra.get("cfrouting_password", ""),
            mailboxes=extra.get("cfrouting_mailboxes", "INBOX"),
            poll_interval_seconds=extra.get("cfrouting_poll_interval_seconds", 2),
            proxy=proxy,
        )
    elif provider == "cfworker":
        return CFWorkerMailbox(
            api_url=extra.get("cfworker_api_url", ""),
            admin_token=extra.get("cfworker_admin_token", ""),
            domain=extra.get("cfworker_domain", ""),
            domain_override=extra.get("cfworker_domain_override", ""),
            domains=extra.get("cfworker_domains", ""),
            enabled_domains=extra.get("cfworker_enabled_domains", ""),
            subdomain=extra.get("cfworker_subdomain", ""),
            domain_level_count=extra.get("email_domain_level_count", 2),
            random_subdomain=extra.get("cfworker_random_subdomain", False),
            random_name_subdomain=extra.get("cfworker_random_name_subdomain", False),
            fingerprint=extra.get("cfworker_fingerprint", ""),
            custom_auth=extra.get("cfworker_custom_auth", ""),
            proxy=proxy,
        )
    elif provider == "luckmail":
        return LuckMailMailbox(
            base_url=extra.get("luckmail_base_url") or "https://mails.luckyous.com/",
            api_key=extra.get("luckmail_api_key", ""),
            project_code=extra.get("luckmail_project_code", ""),
            email_type=extra.get("luckmail_email_type", ""),
            domain=extra.get("luckmail_domain", ""),
            proxy=proxy,
        )
    elif provider in {"outlook", "microsoft"}:
        return OutlookMailbox(
            imap_server=extra.get("outlook_imap_server", ""),
            imap_port=extra.get("outlook_imap_port", ""),
            token_endpoint=extra.get("outlook_token_endpoint", ""),
            backend=extra.get("outlook_backend", ""),
            graph_api_base=extra.get("outlook_graph_api_base", ""),
            proxy=proxy,
        )
    else:  # laoudo
        return LaoudoMailbox(
            auth_token=extra.get("laoudo_auth", ""),
            email=extra.get("laoudo_email", ""),
            account_id=extra.get("laoudo_account_id", ""),
        )


class AppleMailMailbox(BaseMailbox):
    """小苹果取件邮箱服务，基于本地邮箱池文件轮转邮箱账号"""

    def __init__(
        self,
        api_url: str = "https://www.appleemail.top",
        pool_file: str = "",
        pool_dir: str = "mail",
        mailboxes: str = "INBOX,Junk",
        proxy: str = None,
    ):
        self.api = (api_url or "https://www.appleemail.top").rstrip("/")
        self.pool_file = str(pool_file or "").strip()
        self.pool_dir = str(pool_dir or "mail").strip() or "mail"
        self.mailboxes = self._normalize_mailboxes(mailboxes)
        self.proxy = build_requests_proxy_config(proxy)
        self._email = None
        self._selected_record = None
        self._selected_pool_path = None

    @staticmethod
    def _normalize_mailboxes(value: Any) -> list[str]:
        if isinstance(value, (list, tuple, set)):
            items = [str(item or "").strip() for item in value]
        else:
            raw = str(value or "INBOX,Junk").strip() or "INBOX,Junk"
            items = [item.strip() for item in raw.split(",")]

        result = []
        seen = set()
        for item in items:
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result or ["INBOX", "Junk"]

    def _headers(self) -> dict[str, str]:
        return {"accept": "application/json"}

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any],
        timeout: int = 15,
    ) -> Any:
        import requests

        response = requests.request(
            method,
            f"{self.api}{path}",
            params=payload,
            json=None,
            headers=self._headers(),
            proxies=self.proxy,
            timeout=timeout,
        )
        try:
            data = response.json()
        except Exception as exc:
            preview = (response.text or "")[:200]
            raise RuntimeError(
                f"AppleMail API {path} 返回非 JSON: HTTP {response.status_code} {preview}"
            ) from exc

        if response.status_code >= 400:
            if isinstance(data, dict):
                message = (
                    data.get("detail")
                    or data.get("message")
                    or data.get("error")
                    or response.text
                )
            else:
                message = response.text
            raise RuntimeError(
                f"AppleMail API {path} 失败: {str(message or f'HTTP {response.status_code}').strip()}"
            )

        if isinstance(data, dict) and data.get("success") is False:
            message = (
                data.get("message")
                or data.get("detail")
                or data.get("error")
                or "unknown error"
            )
            raise RuntimeError(f"AppleMail API {path} 失败: {str(message).strip()}")

        return data

    @staticmethod
    def _unwrap_message_payload(payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("data", "result", "results", "messages", "mails", "emails", "items", "list"):
                if key in payload:
                    nested = AppleMailMailbox._unwrap_message_payload(payload.get(key))
                    if nested:
                        return nested
            if any(
                key in payload
                for key in (
                    "id",
                    "message_id",
                    "uid",
                    "mail_id",
                    "subject",
                    "content",
                    "text",
                    "html",
                    "body",
                    "preview",
                    "verification_code",
                    "code",
                    "otp",
                )
            ):
                return [payload]

            collected = []
            for value in payload.values():
                collected.extend(AppleMailMailbox._unwrap_message_payload(value))
            return collected
        return []

    @staticmethod
    def _resolve_message_id(message: dict[str, Any], mailbox: str) -> str:
        import hashlib

        for key in ("id", "message_id", "uid", "mail_id", "mid", "_id"):
            value = str(message.get(key) or "").strip()
            if value:
                return value

        raw = json.dumps(message, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha1(f"{mailbox}:{raw}".encode("utf-8")).hexdigest()
        return f"{mailbox}:{digest}"

    def _build_search_text(self, message: dict[str, Any]) -> str:
        parts = []
        for key in (
            "subject",
            "from",
            "from_address",
            "sender",
            "preview",
            "text",
            "content",
            "body",
            "html",
            "html_content",
            "raw",
            "raw_content",
            "mail_text",
        ):
            value = message.get(key)
            if value:
                parts.append(str(value))

        if not parts:
            parts.append(json.dumps(message, ensure_ascii=False))

        text = " ".join(parts).strip()
        return self._decode_raw_content(text) or text

    def _extract_code_from_message(
        self,
        message: dict[str, Any],
        code_pattern: str = None,
    ) -> Optional[str]:
        for key in ("verification_code", "code", "otp", "captcha", "verify_code"):
            value = str(message.get(key) or "").strip()
            if value:
                code = self._safe_extract(value, code_pattern)
                if code:
                    return code
        return self._safe_extract(self._build_search_text(message), code_pattern)

    def _resolve_mailboxes_for_account(self, account: MailboxAccount) -> list[str]:
        account_mailbox = ""
        if isinstance(account.extra, dict):
            account_mailbox = str(account.extra.get("mailbox") or "").strip()

        result = []
        seen = set()
        for mailbox in ([account_mailbox] if account_mailbox else []) + list(self.mailboxes):
            name = str(mailbox or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result or ["INBOX"]

    def _build_request_payload(self, account: MailboxAccount, mailbox: str) -> dict[str, Any]:
        extra = account.extra or {}
        refresh_token = str(extra.get("refresh_token") or "").strip()
        client_id = str(extra.get("client_id") or "").strip()
        if not refresh_token or not client_id:
            raise RuntimeError("AppleMail 邮箱记录缺少 refresh_token 或 client_id")

        return {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "email": account.email,
            "mailbox": mailbox,
        }

    def _list_messages(self, account: MailboxAccount, mailbox: str) -> list[dict[str, Any]]:
        data = self._request_json(
            "GET",
            "/api/mail-all",
            payload=self._build_request_payload(account, mailbox),
            timeout=15,
        )
        if isinstance(data, dict):
            new_refresh_token = str(data.get("new_refresh_token") or "").strip()
            if new_refresh_token:
                if account.extra is None:
                    account.extra = {}
                account.extra["refresh_token"] = new_refresh_token
        return self._unwrap_message_payload(data)

    def get_email(self) -> MailboxAccount:
        from .applemail_pool import take_next_applemail_record

        pool_path, record = take_next_applemail_record(
            pool_file=self.pool_file,
            pool_dir=self.pool_dir,
        )
        self._selected_pool_path = pool_path
        self._selected_record = record
        self._email = record["email"]
        self._log(f"[AppleMail] 使用邮箱池: {pool_path.name}")
        self._log(f"[AppleMail] 分配邮箱: {record['email']}")
        return MailboxAccount(
            email=record["email"],
            account_id=record["email"],
            extra={
                "provider": "applemail",
                "client_id": record["client_id"],
                "refresh_token": record["refresh_token"],
                "mailbox": record.get("mailbox") or "INBOX",
                "pool_file": pool_path.name,
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        ids = set()
        for mailbox in self._resolve_mailboxes_for_account(account):
            try:
                messages = self._list_messages(account, mailbox)
            except Exception:
                continue
            ids.update(
                self._resolve_message_id(message, mailbox)
                for message in messages
            )
        return ids

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }

        def poll_once() -> Optional[str]:
            for mailbox in self._resolve_mailboxes_for_account(account):
                try:
                    messages = self._list_messages(account, mailbox)
                except Exception:
                    continue

                for message in messages:
                    message_id = self._resolve_message_id(message, mailbox)
                    if message_id in seen:
                        continue
                    seen.add(message_id)

                    search_text = self._build_search_text(message)
                    if keyword and keyword.lower() not in search_text.lower():
                        continue

                    code = self._extract_code_from_message(message, code_pattern)
                    if code and code in exclude_codes:
                        continue
                    if code:
                        self._log(f"[AppleMail] {mailbox} 收到验证码: {code}")
                        return code
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class LaoudoMailbox(BaseMailbox):
    """laoudo.com 邮箱服务"""

    def __init__(self, auth_token: str, email: str, account_id: str):
        self.auth = auth_token
        self._email = email
        self._account_id = account_id
        self.api = "https://laoudo.com/api/email"
        self._ua = "Mozilla/5.0"

    def get_email(self) -> MailboxAccount:
        if not self._email:
            raise RuntimeError(
                "Laoudo 邮箱未配置或已失效，请检查 laoudo_auth、laoudo_email、laoudo_account_id 配置，"
                "或切换到 tempmail_lol（无需配置）"
            )
        return MailboxAccount(email=self._email, account_id=self._account_id)

    def get_current_ids(self, account: MailboxAccount) -> set:
        from curl_cffi import requests as curl_requests

        try:
            r = curl_requests.get(
                f"{self.api}/list",
                params={
                    "accountId": account.account_id,
                    "allReceive": 0,
                    "emailId": 0,
                    "timeSort": 1,
                    "size": 50,
                    "type": 0,
                },
                headers={"authorization": self.auth, "user-agent": self._ua},
                timeout=15,
                impersonate="chrome131",
            )
            if r.status_code == 200:
                mails = r.json().get("data", {}).get("list", []) or []
                return {
                    m.get("id") or m.get("emailId")
                    for m in mails
                    if m.get("id") or m.get("emailId")
                }
        except Exception:
            pass
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
        from curl_cffi import requests as curl_requests

        seen = set(before_ids) if before_ids else set()
        h = {"authorization": self.auth, "user-agent": self._ua}

        def poll_once() -> Optional[str]:
            try:
                r = curl_requests.get(
                    f"{self.api}/list",
                    params={
                        "accountId": account.account_id,
                        "allReceive": 0,
                        "emailId": 0,
                        "timeSort": 1,
                        "size": 50,
                        "type": 0,
                    },
                    headers=h,
                    timeout=15,
                    impersonate="chrome131",
                )
                if r.status_code == 200:
                    mails = r.json().get("data", {}).get("list", []) or []
                    for mail in mails:
                        mid = mail.get("id") or mail.get("emailId")
                        if not mid or mid in seen:
                            continue
                        seen.add(mid)
                        text = (
                            str(mail.get("subject", ""))
                            + " "
                            + str(mail.get("content") or mail.get("html") or "")
                        )
                        if keyword and keyword.lower() not in text.lower():
                            continue
                        code = self._safe_extract(text, code_pattern)
                        if code:
                            return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=4,
            poll_once=poll_once,
        )


class AitreMailbox(BaseMailbox):
    """mail.aitre.cc 临时邮箱"""

    def __init__(self, email: str):
        self._email = email
        self.api = "https://mail.aitre.cc/api/tempmail"

    def get_email(self) -> MailboxAccount:
        return MailboxAccount(email=self._email)

    def get_current_ids(self, account: MailboxAccount) -> set:
        import requests

        try:
            r = requests.get(
                f"{self.api}/emails", params={"email": account.email}, timeout=10
            )
            emails = r.json().get("emails", [])
            return {str(m["id"]) for m in emails if "id" in m}
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
        import requests

        seen = set(before_ids) if before_ids else set()
        last_check = None

        def poll_once() -> Optional[str]:
            nonlocal last_check
            params = {"email": account.email}
            if last_check:
                params["lastCheck"] = last_check
            try:
                r = requests.get(f"{self.api}/poll", params=params, timeout=10)
                data = r.json()
                last_check = data.get("lastChecked")
                if data.get("count", 0) > 0:
                    r2 = requests.get(
                        f"{self.api}/emails",
                        params={"email": account.email},
                        timeout=10,
                    )
                    for mail in r2.json().get("emails", []):
                        mid = str(mail.get("id", ""))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        text = mail.get("preview", "") + mail.get("content", "")
                        if keyword and keyword.lower() not in text.lower():
                            continue
                        code = self._safe_extract(text, code_pattern)
                        if code:
                            return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class TempMailLolMailbox(BaseMailbox):
    """tempmail.lol 免费临时邮箱（无需注册，自动生成）"""

    def __init__(self, proxy: str = None):
        self.api = "https://api.tempmail.lol/v2"
        self.proxy = build_requests_proxy_config(proxy)
        self._token = None
        self._email = None

    def get_email(self) -> MailboxAccount:
        import requests

        r = requests.post(
            f"{self.api}/inbox/create", json={}, proxies=self.proxy, timeout=15
        )
        data = r.json()
        email = data.get("address") or data.get("email", "")
        if not email:
            raise RuntimeError(f"tempmail.lol API 返回空邮箱: {data}")
        self._email = email
        self._token = data.get("token", "")
        print(f"[TempMailLol] 生成邮箱: {self._email}")
        return MailboxAccount(email=self._email, account_id=self._token)

    def get_current_ids(self, account: MailboxAccount) -> set:
        import requests

        try:
            r = requests.get(
                f"{self.api}/inbox",
                params={"token": account.account_id},
                proxies=self.proxy,
                timeout=10,
            )
            return {str(m["id"]) for m in r.json().get("emails", [])}
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
        import requests

        seen = set(before_ids or [])
        otp_sent_at = kwargs.get("otp_sent_at")

        def poll_once() -> Optional[str]:
            try:
                r = requests.get(
                    f"{self.api}/inbox",
                    params={"token": account.account_id},
                    proxies=self.proxy,
                    timeout=10,
                )
                for mail in sorted(
                    r.json().get("emails", []),
                    key=lambda x: x.get("date", 0),
                    reverse=True,
                ):
                    mid = str(mail.get("id", ""))
                    if mid in seen:
                        continue
                    if otp_sent_at and mail.get("date", 0) / 1000 < otp_sent_at:
                        continue
                    seen.add(mid)
                    text = (
                        mail.get("subject", "")
                        + " "
                        + mail.get("body", "")
                        + " "
                        + mail.get("html", "")
                    )
                    if keyword and keyword.lower() not in text.lower():
                        continue
                    code = self._safe_extract(text, code_pattern)
                    if code:
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class SkyMailMailbox(BaseMailbox):
    """SkyMail / CloudMail 自建邮箱服务"""

    def __init__(self, api_base: str, auth_token: str, domain: str, proxy: str = None):
        self.api = (api_base or "").rstrip("/")
        self.auth_token = auth_token or ""
        self.domain = domain or ""
        self.proxy = build_requests_proxy_config(proxy)

    def _headers(self) -> dict:
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": self.auth_token,
        }

    def _ensure_config(self) -> None:
        if not self.api or not self.auth_token or not self.domain:
            raise RuntimeError(
                "SkyMail 未配置完整：请设置 skymail_api_base、skymail_token、skymail_domain"
            )

    def _gen_prefix(self) -> str:
        import random
        import string

        length = random.randint(8, 13)
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    def get_email(self) -> MailboxAccount:
        import requests

        self._ensure_config()
        email = f"{self._gen_prefix()}@{self.domain}"
        payload = {"list": [{"email": email}]}
        r = requests.post(
            f"{self.api}/api/public/addUser",
            json=payload,
            headers=self._headers(),
            proxies=self.proxy,
            timeout=15,
        )
        if r.status_code != 200:
            raise RuntimeError(f"SkyMail 创建邮箱失败: {r.status_code} {r.text[:200]}")

        data = r.json()
        if data.get("code") != 200:
            raise RuntimeError(f"SkyMail 创建邮箱失败: {data}")

        self._log(f"[SkyMail] 生成邮箱: {email}")
        return MailboxAccount(email=email, account_id=email)

    def _list_mails(self, email: str) -> list:
        import requests

        payload = {
            "toEmail": email,
            "num": 1,
            "size": 20,
        }
        r = requests.post(
            f"{self.api}/api/public/emailList",
            json=payload,
            headers=self._headers(),
            proxies=self.proxy,
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if data.get("code") != 200:
            return []
        return data.get("data") or []

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            mails = self._list_mails(account.account_id or account.email)
            ids = set()
            for i, msg in enumerate(mails):
                mid = msg.get("id") or msg.get("mailId") or msg.get("messageId")
                if mid:
                    ids.add(str(mid))
                else:
                    digest = (
                        str(msg.get("date") or msg.get("time") or "")
                        + "|"
                        + str(msg.get("subject") or "")
                    )
                    ids.add(f"idx-{i}-{digest}")
            return ids
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
        target = account.account_id or account.email
        seen = set(before_ids or [])

        def poll_once() -> Optional[str]:
            try:
                mails = self._list_mails(target)
                for i, msg in enumerate(mails):
                    mid = msg.get("id") or msg.get("mailId") or msg.get("messageId")
                    if not mid:
                        digest = (
                            str(msg.get("date") or msg.get("time") or "")
                            + "|"
                            + str(msg.get("subject") or "")
                        )
                        mid = f"idx-{i}-{digest}"
                    mid = str(mid)
                    if mid in seen:
                        continue
                    seen.add(mid)

                    content = " ".join(
                        [
                            str(msg.get("subject") or ""),
                            str(msg.get("content") or ""),
                            str(msg.get("text") or ""),
                            str(msg.get("html") or ""),
                        ]
                    )
                    if keyword and keyword.lower() not in content.lower():
                        continue

                    code = self._safe_extract(content, code_pattern)
                    if code:
                        self._log(f"[SkyMail] 命中验证码: {code}")
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class CloudMailMailbox(BaseMailbox):
    """CloudMail 自建邮箱服务（genToken + emailList）"""

    _token_lock = threading.Lock()
    _token_cache: dict[str, tuple[str, float]] = {}
    _seen_ids_lock = threading.Lock()
    _seen_ids: dict[str, set[str]] = {}

    def __init__(
        self,
        api_base: str,
        admin_email: str,
        admin_password: str,
        domain: Any = "",
        subdomain: str = "",
        timeout: int = 30,
        proxy: str = None,
    ):
        self.api = str(api_base or "").rstrip("/")
        self.admin_email = str(admin_email or "").strip()
        self.admin_password = str(admin_password or "").strip()
        self.domain = domain
        self.subdomain = str(subdomain or "").strip()
        self.timeout = max(int(timeout or 30), 5)
        self.proxy = build_requests_proxy_config(proxy)

    @staticmethod
    def _extract_domain_from_url(url: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(str(url or ""))
        host = (parsed.netloc or parsed.path.split("/")[0] or "").strip()
        if ":" in host:
            host = host.split(":", 1)[0].strip()
        return host

    @staticmethod
    def _normalize_domain(value: str) -> str:
        domain = str(value or "").strip().lstrip("@")
        if "://" in domain:
            domain = CloudMailMailbox._extract_domain_from_url(domain)
        return domain.strip()

    def _domain_candidates(self) -> list[str]:
        candidates: list[str] = []

        if isinstance(self.domain, (list, tuple, set)):
            iterable = self.domain
        else:
            raw = str(self.domain or "").strip()
            parsed = None
            if raw.startswith("[") and raw.endswith("]"):
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = None
            if isinstance(parsed, list):
                iterable = parsed
            elif raw:
                normalized = (
                    raw.replace(";", "\n")
                    .replace(",", "\n")
                    .replace("|", "\n")
                    .splitlines()
                )
                iterable = [item for item in normalized if item]
            else:
                iterable = []

        for item in iterable:
            normalized = self._normalize_domain(item)
            if normalized:
                candidates.append(normalized)

        if not candidates:
            inferred = self._normalize_domain(self._extract_domain_from_url(self.api))
            if inferred:
                candidates.append(inferred)
        return candidates

    def _resolve_admin_email(self) -> str:
        if self.admin_email:
            return self.admin_email
        domains = self._domain_candidates()
        if domains:
            return f"admin@{domains[0]}"
        return "admin@example.com"

    def _cache_key(self) -> str:
        return f"{self.api}|{self._resolve_admin_email()}|{self.admin_password}"

    def _ensure_config(self) -> None:
        if not self.api or not self.admin_password:
            raise RuntimeError(
                "CloudMail 未配置完整：请设置 cloudmail_api_base 与 cloudmail_admin_password"
            )

    def _headers(self, token: str = "") -> dict:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if token:
            headers["authorization"] = token
        return headers

    def _generate_token(self) -> str:
        import requests

        self._ensure_config()
        payload = {
            "email": self._resolve_admin_email(),
            "password": self.admin_password,
        }
        r = requests.post(
            f"{self.api}/api/public/genToken",
            json=payload,
            headers=self._headers(),
            proxies=self.proxy,
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"CloudMail 生成 token 失败: {r.status_code} {str(r.text or '')[:200]}"
            )

        try:
            data = r.json()
        except Exception:
            data = {}
        if data.get("code") != 200:
            raise RuntimeError(f"CloudMail 生成 token 失败: {data}")
        token = ((data.get("data") or {}).get("token") or "").strip()
        if not token:
            raise RuntimeError("CloudMail 生成 token 失败: 响应未返回 token")
        return token

    def _get_token(self, *, force_refresh: bool = False) -> str:
        cache_key = self._cache_key()
        now = time.time()
        with CloudMailMailbox._token_lock:
            if not force_refresh:
                cached = CloudMailMailbox._token_cache.get(cache_key)
                if cached and now < cached[1]:
                    return cached[0]

            token = self._generate_token()
            CloudMailMailbox._token_cache[cache_key] = (token, now + 3600)
            return token

    def _list_mails(self, email: str, *, retry_auth: bool = True) -> list:
        import requests

        token = self._get_token()
        payload = {
            "toEmail": email,
            "timeSort": "desc",
        }
        r = requests.post(
            f"{self.api}/api/public/emailList",
            json=payload,
            headers=self._headers(token),
            proxies=self.proxy,
            timeout=self.timeout,
        )
        if r.status_code == 401 and retry_auth:
            token = self._get_token(force_refresh=True)
            r = requests.post(
                f"{self.api}/api/public/emailList",
                json=payload,
                headers=self._headers(token),
                proxies=self.proxy,
                timeout=self.timeout,
            )
        if r.status_code != 200:
            return []

        try:
            data = r.json()
        except Exception:
            data = {}
        if data.get("code") != 200:
            return []
        return data.get("data") or []

    def _gen_prefix(self) -> str:
        import random
        import string

        first = random.choice(string.ascii_lowercase)
        rest = "".join(random.choices(string.ascii_lowercase + string.digits, k=9))
        return first + rest

    def _build_email(self) -> str:
        domains = self._domain_candidates()
        if not domains:
            raise RuntimeError("CloudMail 未配置可用域名")
        domain = random.choice(domains)
        if self.subdomain:
            domain = f"{self.subdomain}.{domain}"
        return f"{self._gen_prefix()}@{domain}"

    @staticmethod
    def _parse_message_timestamp(message: dict) -> Optional[float]:
        from datetime import datetime

        keys = [
            "time",
            "date",
            "created",
            "createdAt",
            "created_at",
            "receivedAt",
            "received_at",
            "sendTime",
            "timestamp",
        ]
        for key in keys:
            value = message.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, (int, float)):
                numeric = float(value)
                return numeric / 1000 if numeric > 10_000_000_000 else numeric
            text = str(value).strip()
            if not text:
                continue
            try:
                numeric = float(text)
                return numeric / 1000 if numeric > 10_000_000_000 else numeric
            except (TypeError, ValueError):
                pass
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
        return None

    @staticmethod
    def _mail_id(message: dict, index: int = 0) -> str:
        for key in ("emailId", "id", "mailId", "messageId"):
            value = message.get(key)
            if value not in (None, ""):
                return str(value)
        digest = (
            str(message.get("date") or message.get("time") or "")
            + "|"
            + str(message.get("subject") or "")
        )
        return f"idx-{index}-{digest}"

    def _remember_seen_id(self, email: str, message_id: str) -> None:
        with CloudMailMailbox._seen_ids_lock:
            CloudMailMailbox._seen_ids.setdefault(email, set()).add(message_id)

    def _load_seen_ids(self, email: str) -> set[str]:
        with CloudMailMailbox._seen_ids_lock:
            return set(CloudMailMailbox._seen_ids.get(email, set()))

    def get_email(self) -> MailboxAccount:
        self._ensure_config()
        email = self._build_email()
        self._log(f"[CloudMail] 生成邮箱: {email}")
        return MailboxAccount(email=email, account_id=email)

    def get_current_ids(self, account: MailboxAccount) -> set:
        target = account.account_id or account.email
        try:
            mails = self._list_mails(target)
            return {self._mail_id(msg, idx) for idx, msg in enumerate(mails)}
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
        target = account.account_id or account.email
        seen = set(before_ids or set())
        seen.update(self._load_seen_ids(target))
        otp_sent_at = kwargs.get("otp_sent_at")
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }

        def poll_once() -> Optional[str]:
            try:
                mails = self._list_mails(target)
                for idx, msg in enumerate(mails):
                    mid = self._mail_id(msg, idx)
                    if mid in seen:
                        continue
                    seen.add(mid)
                    self._remember_seen_id(target, mid)

                    msg_ts = self._parse_message_timestamp(msg)
                    if otp_sent_at and msg_ts and msg_ts < float(otp_sent_at):
                        continue

                    content = " ".join(
                        [
                            str(msg.get("subject") or ""),
                            str(msg.get("content") or ""),
                            str(msg.get("text") or ""),
                            str(msg.get("html") or ""),
                        ]
                    )
                    if keyword and keyword.lower() not in content.lower():
                        continue
                    code = self._safe_extract(content, code_pattern)
                    if code and code in exclude_codes:
                        continue
                    if code:
                        self._log(f"[CloudMail] 命中验证码: {code}")
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class DuckMailMailbox(BaseMailbox):
    """DuckMail 自动生成邮箱（随机创建账号）"""

    def __init__(
        self,
        api_url: str = "https://www.duckmail.sbs",
        provider_url: str = "https://api.duckmail.sbs",
        bearer: str = "kevin273945",
        domain: str = "",
        api_key: str = "",
        proxy: str = None,
    ):
        self.api = (api_url or "https://www.duckmail.sbs").rstrip("/")
        self.provider_url = (provider_url or "https://api.duckmail.sbs").rstrip("/")
        self.bearer = bearer or "kevin273945"
        self.domain = str(domain or "").strip()
        self.api_key = str(api_key or "").strip()
        self.proxy = build_requests_proxy_config(proxy)
        self._token = None
        self._address = None
        # 如果配置了 API Key，直接请求 DuckMail API；否则走前端代理
        self._direct = bool(self.api_key)

    def _proxy_headers(self) -> dict:
        return {
            "authorization": f"Bearer {self.bearer}",
            "content-type": "application/json",
            "x-api-provider-base-url": self.provider_url,
        }

    def _direct_headers(self, token: str = "") -> dict:
        auth = token or self.api_key
        return {
            "authorization": f"Bearer {auth}",
            "content-type": "application/json",
        }

    def _request(self, method: str, endpoint: str, token: str = "", **kwargs):
        """统一请求方法，根据模式选择直连或代理"""
        import requests

        if self._direct:
            url = f"{self.provider_url}{endpoint}"
            headers = self._direct_headers(token)
        else:
            from urllib.parse import quote

            url = f"{self.api}/api/mail?endpoint={quote(endpoint, safe='')}"
            headers = (
                self._proxy_headers()
                if not token
                else {
                    "authorization": f"Bearer {token}",
                    "x-api-provider-base-url": self.provider_url,
                }
            )
        r = requests.request(
            method, url, headers=headers, proxies=self.proxy, timeout=15, **kwargs
        )
        return r

    def get_email(self) -> MailboxAccount:
        import string

        username = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        password = "Test" + "".join(random.choices(string.digits, k=8)) + "!"
        domain = self.domain or self.provider_url.replace("https://api.", "").replace(
            "https://", ""
        )
        address = f"{username}@{domain}"
        print(f"[DuckMail] 创建账号: {address} direct={self._direct}")
        # 创建账号
        r = self._request(
            "POST", "/accounts", json={"address": address, "password": password}
        )
        if r.status_code >= 400 or not r.text.strip().startswith("{"):
            raise RuntimeError(
                f"[DuckMail] 创建账号失败: HTTP {r.status_code} body={r.text[:300]}"
            )
        data = r.json()
        self._address = data.get("address", address)
        # 登录获取 token
        r2 = self._request(
            "POST", "/token", json={"address": self._address, "password": password}
        )
        if r2.status_code >= 400 or not r2.text.strip().startswith(("{", "[")):
            raise RuntimeError(
                f"[DuckMail] 登录失败: HTTP {r2.status_code} body={r2.text[:300]}"
            )
        self._token = r2.json().get("token", "")
        return MailboxAccount(email=self._address, account_id=self._token)

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            r = self._request("GET", "/messages?page=1", token=account.account_id)
            return {str(m["id"]) for m in r.json().get("hydra:member", [])}
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
        import re
        from datetime import datetime

        seen = set(before_ids or [])
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }
        otp_sent_at = kwargs.get("otp_sent_at")

        def _parse_message_timestamp(*values) -> Optional[float]:
            for value in values:
                if value in (None, ""):
                    continue
                if isinstance(value, (int, float)):
                    numeric = float(value)
                    return numeric / 1000 if numeric > 10_000_000_000 else numeric
                text = str(value).strip()
                if not text:
                    continue
                try:
                    numeric = float(text)
                    return numeric / 1000 if numeric > 10_000_000_000 else numeric
                except (TypeError, ValueError):
                    pass
                try:
                    normalized = text.replace("Z", "+00:00")
                    return datetime.fromisoformat(normalized).timestamp()
                except ValueError:
                    continue
            return None

        def poll_once() -> Optional[str]:
            try:
                r = self._request("GET", "/messages?page=1", token=account.account_id)
                msgs = r.json().get("hydra:member", [])
                for msg in msgs:
                    mid = str(msg.get("id") or msg.get("msgid") or "")
                    if mid in seen:
                        continue
                    seen.add(mid)
                    # 请求邮件详情获取完整 text
                    try:
                        r2 = self._request(
                            "GET", f"/messages/{mid}", token=account.account_id
                        )
                        detail = r2.json()
                        body = (
                            str(detail.get("text") or "")
                            + " "
                            + str(detail.get("subject") or "")
                        )
                    except Exception:
                        detail = {}
                        body = str(msg.get("subject") or "")
                    message_ts = _parse_message_timestamp(
                        detail.get("createdAt"),
                        detail.get("created_at"),
                        detail.get("receivedAt"),
                        detail.get("received_at"),
                        detail.get("date"),
                        detail.get("created"),
                        msg.get("createdAt"),
                        msg.get("created_at"),
                        msg.get("receivedAt"),
                        msg.get("received_at"),
                        msg.get("date"),
                        msg.get("created"),
                    )
                    if otp_sent_at and message_ts and message_ts < float(otp_sent_at):
                        continue
                    body = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "", body
                    )
                    code = self._safe_extract(body, code_pattern)
                    if code and code in exclude_codes:
                        continue
                    if code:
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class MaliAPIMailbox(BaseMailbox):
    """YYDS Mail / MaliAPI 临时邮箱服务"""

    def __init__(
        self,
        api_url: str = "https://maliapi.215.im/v1",
        api_key: str = "",
        domain: str = "",
        auto_domain_strategy: str = "",
        proxy: str = None,
    ):
        self.api = (api_url or "https://maliapi.215.im/v1").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.domain = str(domain or "").strip()
        self.auto_domain_strategy = str(auto_domain_strategy or "").strip()
        self.proxy = build_requests_proxy_config(proxy)
        self._email = None
        self._temp_token = None

    def _headers(self, bearer: str = "") -> dict[str, str]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict = None,
        params: dict = None,
        bearer: str = "",
    ) -> Any:
        import requests

        response = requests.request(
            method,
            f"{self.api}{path}",
            headers=self._headers(bearer),
            json=json_body,
            params=params,
            proxies=self.proxy,
            timeout=15,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {}

        if response.status_code >= 400:
            error = response.text or f"HTTP {response.status_code}"
            error_code = ""
            if isinstance(payload, dict):
                error = str(payload.get("error") or error).strip()
                error_code = str(payload.get("errorCode") or "").strip()
            if error_code:
                raise RuntimeError(f"MaliAPI 请求失败: {error} ({error_code})")
            raise RuntimeError(f"MaliAPI 请求失败: {str(error).strip()}")

        if isinstance(payload, dict):
            if payload.get("success") is False:
                error = str(payload.get("error") or "unknown error").strip()
                error_code = str(payload.get("errorCode") or "").strip()
                if error_code:
                    raise RuntimeError(f"MaliAPI 请求失败: {error} ({error_code})")
                raise RuntimeError(f"MaliAPI 请求失败: {error}")
            if "data" in payload:
                return payload.get("data")
        return payload

    def _ensure_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError("MaliAPI 未配置：请在全局设置中填写 maliapi_api_key")

    def _list_messages(self, account: MailboxAccount) -> list[dict]:
        data = self._request("GET", "/messages", params={"address": account.email})
        if isinstance(data, dict):
            messages = data.get("messages", [])
        else:
            messages = data
        return [item for item in (messages or []) if isinstance(item, dict)]

    def _get_message_detail(self, message_id: str) -> dict:
        data = self._request("GET", f"/messages/{message_id}")
        if isinstance(data, dict) and isinstance(data.get("message"), dict):
            return data["message"]
        return data if isinstance(data, dict) else {}

    def get_email(self) -> MailboxAccount:
        self._ensure_api_key()
        body = {}
        if self.domain:
            body["domain"] = self.domain
        if self.auto_domain_strategy:
            body["autoDomainStrategy"] = self.auto_domain_strategy

        data = self._request("POST", "/accounts", json_body=body)
        if not isinstance(data, dict):
            raise RuntimeError(f"MaliAPI 返回异常: {data}")

        email = str(data.get("address") or data.get("email") or "").strip()
        temp_token = str(
            data.get("tempToken") or data.get("temp_token") or data.get("token") or ""
        ).strip()
        inbox_id = str(data.get("id") or "").strip()
        if not email:
            raise RuntimeError(f"MaliAPI 返回空邮箱: {data}")

        self._email = email
        self._temp_token = temp_token
        self._log(f"[MaliAPI] 生成邮箱: {email}")
        return MailboxAccount(
            email=email,
            account_id=temp_token or inbox_id or email,
            extra={
                "provider": "maliapi",
                "temp_token": temp_token,
                "inbox_id": inbox_id,
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        self._ensure_api_key()
        try:
            return {
                str(message.get("id"))
                for message in self._list_messages(account)
                if message.get("id") is not None
            }
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
        import re

        self._ensure_api_key()
        seen = {str(mid) for mid in (before_ids or set())}

        def poll_once() -> Optional[str]:
            try:
                for message in self._list_messages(account):
                    message_id = str(message.get("id") or "").strip()
                    if not message_id or message_id in seen:
                        continue
                    seen.add(message_id)

                    try:
                        detail = self._get_message_detail(message_id)
                    except Exception:
                        detail = message

                    search_text = " ".join(
                        [
                            str(detail.get("subject") or message.get("subject") or ""),
                            str(detail.get("text") or ""),
                            str(detail.get("html") or ""),
                            str(message.get("subject") or ""),
                            str(message.get("snippet") or ""),
                        ]
                    ).strip()
                    search_text = self._yyds_decode_raw_content(search_text) or search_text
                    search_text = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                        "",
                        search_text,
                    )
                    if keyword and keyword.lower() not in search_text.lower():
                        continue

                    code = self._yyds_safe_extract(search_text, code_pattern)
                    if code:
                        self._log(f"[MaliAPI] 收到验证码: {code}")
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class GPTMailMailbox(BaseMailbox):
    """GPTMail 临时邮箱服务"""

    def __init__(
        self,
        api_url: str = "https://mail.chatgpt.org.uk",
        api_key: str = "",
        domain: str = "",
        mode: str = "api",
        proxy: str = None,
    ):
        self.api = (api_url or "https://mail.chatgpt.org.uk").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.domain = self._normalize_domain(domain)
        self.mode = self._normalize_mode(mode)
        self._proxy_url = proxy
        self.proxy = build_requests_proxy_config(proxy)
        self._email = None
        self._automation_client = None

    @staticmethod
    def _normalize_domain(value: Any) -> str:
        domain = str(value or "").strip().lower()
        if domain.startswith("@"):
            domain = domain[1:]
        return domain

    @staticmethod
    def _normalize_mode(value: Any) -> str:
        mode = str(value or "api").strip().lower() or "api"
        if mode not in {"api", "automation"}:
            raise RuntimeError(f"GPTMail 模式不支持: {mode}")
        return mode

    @staticmethod
    def _generate_local_part() -> str:
        import string

        prefix = "".join(random.choices(string.ascii_lowercase, k=6))
        suffix = "".join(random.choices(string.digits, k=4))
        return f"{prefix}{suffix}"

    def _get_automation_client(self):
        if self._automation_client is None:
            from .gptmail_automation import GPTMailAutomationClient

            self._automation_client = GPTMailAutomationClient(
                api_base=self.api,
                proxy_url=self._proxy_url,
            )
        return self._automation_client

    @staticmethod
    def _resolve_message_id(message: dict[str, Any]) -> str:
        import hashlib

        for key in ("id", "message_id", "uid", "mail_id", "_id"):
            value = str(message.get(key) or "").strip()
            if value:
                return value

        raw = json.dumps(message, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self.mode == "api" and self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        timeout: int = 15,
    ) -> Any:
        import requests

        response = requests.request(
            method,
            f"{self.api}{path}",
            params=params,
            json=json_body,
            headers=self._headers(),
            proxies=self.proxy,
            timeout=timeout,
        )
        try:
            payload = response.json()
        except Exception as exc:
            preview = (response.text or "")[:200]
            raise RuntimeError(
                f"GPTMail API {path} 返回非 JSON: HTTP {response.status_code} {preview}"
            ) from exc

        if response.status_code >= 400:
            error = payload.get("error") if isinstance(payload, dict) else ""
            message = str(error or response.text or f"HTTP {response.status_code}").strip()
            raise RuntimeError(f"GPTMail API {path} 失败: {message}")

        if isinstance(payload, dict) and payload.get("success") is False:
            error = str(payload.get("error") or "unknown error").strip()
            raise RuntimeError(f"GPTMail API {path} 失败: {error}")

        if isinstance(payload, dict) and "data" in payload:
            return payload.get("data")
        return payload

    def _list_messages(self, email: str) -> list[dict]:
        if self.mode == "automation":
            return self._get_automation_client().get_emails(email)

        data = self._request_json("GET", "/api/emails", params={"email": email}, timeout=10)
        if isinstance(data, dict):
            messages = data.get("emails", [])
        else:
            messages = data
        return [item for item in (messages or []) if isinstance(item, dict)]

    def _get_message_detail(self, message_id: str) -> dict[str, Any]:
        if self.mode == "automation":
            return {}
        data = self._request_json("GET", f"/api/email/{message_id}", timeout=10)
        return data if isinstance(data, dict) else {}

    def get_email(self) -> MailboxAccount:
        if self.domain:
            email = f"{self._generate_local_part()}@{self.domain}"
            self._email = email
            self._log(f"[GPTMail] 本地拼装邮箱: {email}")
            return MailboxAccount(
                email=email,
                account_id=email,
                extra={
                    "provider": "gptmail",
                    "mode": self.mode,
                    "domain": self.domain,
                    "local_address": True,
                },
            )

        if self.mode == "automation":
            email = self._get_automation_client().generate_email()
        else:
            data = self._request_json("GET", "/api/generate-email")
            if not isinstance(data, dict):
                raise RuntimeError(f"GPTMail 返回异常: {data}")
            email = str(data.get("email") or "").strip()
            if not email:
                raise RuntimeError(f"GPTMail 返回空邮箱: {data}")

        self._email = email
        self._log(f"[GPTMail/{self.mode}] 生成邮箱: {email}")
        return MailboxAccount(
            email=email,
            account_id=email,
            extra={"provider": "gptmail", "mode": self.mode},
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            return {
                self._resolve_message_id(message)
                for message in self._list_messages(account.email)
                if self._resolve_message_id(message)
            }
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
        import re

        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {
            str(code) for code in (kwargs.get("exclude_codes") or set()) if code
        }

        def poll_once() -> Optional[str]:
            try:
                messages = self._list_messages(account.email)
                for message in messages:
                    message_id = self._resolve_message_id(message)
                    if not message_id or message_id in seen:
                        continue
                    seen.add(message_id)

                    try:
                        detail = self._get_message_detail(message_id)
                    except Exception:
                        detail = {}

                    search_text = " ".join(
                        [
                            str(message.get("subject") or ""),
                            str(message.get("from_address") or ""),
                            str(message.get("text") or ""),
                            str(message.get("html") or ""),
                            str(message.get("content") or ""),
                            str(message.get("html_content") or ""),
                            str(detail.get("subject") or ""),
                            str(detail.get("text") or ""),
                            str(detail.get("html") or ""),
                            str(detail.get("content") or ""),
                            str(detail.get("html_content") or ""),
                            str(detail.get("raw_headers") or ""),
                        ]
                    ).strip()
                    search_text = self._decode_raw_content(search_text) or search_text
                    search_text = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                        "",
                        search_text,
                    )
                    if keyword and keyword.lower() not in search_text.lower():
                        continue

                    code = self._safe_extract(search_text, code_pattern)
                    if code and code in exclude_codes:
                        continue
                    if code:
                        self._log(f"[GPTMail] 收到验证码: {code}")
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class OpenTrashMailMailbox(BaseMailbox):
    """OpenTrashMail 临时邮箱服务"""

    def __init__(
        self,
        api_url: str = "",
        domain: str = "",
        password: str = "",
        proxy: str = None,
    ):
        self.api = str(api_url or "").strip().rstrip("/")
        self.domain = self._normalize_domain(domain)
        self.password = str(password or "").strip()
        self.proxy = build_requests_proxy_config(proxy)

    @staticmethod
    def _normalize_domain(value: Any) -> str:
        domain = str(value or "").strip().lower()
        if domain.startswith("@"):
            domain = domain[1:]
        return domain

    @staticmethod
    def _generate_local_part() -> str:
        import string

        prefix = "".join(random.choices(string.ascii_lowercase, k=8))
        suffix = "".join(random.choices(string.digits, k=2))
        return f"{prefix}{suffix}"

    def _headers(self) -> dict[str, str]:
        return {"accept": "application/json, text/plain, */*"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        timeout: int = 15,
    ):
        import requests

        request_params = dict(params or {})
        if self.password and "password" not in request_params:
            request_params["password"] = self.password

        return requests.request(
            method,
            f"{self.api}{path}",
            params=request_params or None,
            json=None,
            headers=self._headers(),
            proxies=self.proxy,
            timeout=timeout,
        )

    def _require_api(self) -> None:
        if not self.api:
            raise RuntimeError(
                "OpenTrashMail 未配置 API URL，请检查 opentrashmail_api_url"
            )

    def _build_email_path(self, email: str) -> str:
        from urllib.parse import quote

        return quote(str(email or "").strip(), safe="@")

    def _parse_random_email(self, html_text: str) -> str:
        import re

        text = str(html_text or "")
        if not text:
            return ""

        match = re.search(r"/address/([^\"'<>\s]+@[^\"'<>\s]+)", text, re.IGNORECASE)
        if match:
            return str(match.group(1) or "").strip()

        match = re.search(
            r"([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})",
            text,
            re.IGNORECASE,
        )
        if match:
            return str(match.group(1) or "").strip()
        return ""

    def _list_messages(self, email: str) -> list[dict[str, Any]]:
        self._require_api()
        response = self._request(
            "GET",
            f"/json/{self._build_email_path(email)}",
            timeout=10,
        )
        if response.status_code == 404:
            return []
        try:
            payload = response.json()
        except Exception as exc:
            preview = (response.text or "")[:200]
            raise RuntimeError(
                f"OpenTrashMail 收件箱返回非 JSON: HTTP {response.status_code} {preview}"
            ) from exc

        if response.status_code >= 400:
            if isinstance(payload, dict) and payload.get("error"):
                error = payload.get("error")
            else:
                error = response.text or f"HTTP {response.status_code}"
            raise RuntimeError(f"OpenTrashMail 收件箱查询失败: {str(error).strip()}")

        if not payload:
            return []

        messages: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            for message_id, item in payload.items():
                if not isinstance(item, dict):
                    continue
                message = dict(item)
                message.setdefault("id", str(message_id))
                messages.append(message)
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    messages.append(item)
        return messages

    def _get_message_detail(self, email: str, message_id: str) -> dict[str, Any]:
        self._require_api()
        response = self._request(
            "GET",
            f"/json/{self._build_email_path(email)}/{message_id}",
            timeout=10,
        )
        if response.status_code == 404:
            return {}
        try:
            payload = response.json()
        except Exception as exc:
            preview = (response.text or "")[:200]
            raise RuntimeError(
                f"OpenTrashMail 邮件详情返回非 JSON: HTTP {response.status_code} {preview}"
            ) from exc

        if response.status_code >= 400:
            if isinstance(payload, dict) and payload.get("error"):
                error = payload.get("error")
            else:
                error = response.text or f"HTTP {response.status_code}"
            raise RuntimeError(f"OpenTrashMail 邮件详情查询失败: {str(error).strip()}")

        return payload if isinstance(payload, dict) else {}

    def get_email(self) -> MailboxAccount:
        if self.domain:
            email = f"{self._generate_local_part()}@{self.domain}"
            self._log(f"[OpenTrashMail] 本地拼装邮箱: {email}")
            return MailboxAccount(
                email=email,
                account_id=email,
                extra={
                    "provider": "opentrashmail",
                    "domain": self.domain,
                    "local_address": True,
                },
            )

        self._require_api()
        response = self._request("GET", "/api/random", timeout=15)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenTrashMail 随机邮箱生成失败: HTTP {response.status_code}"
            )

        email = self._parse_random_email(response.text)
        if not email:
            preview = (response.text or "")[:200]
            raise RuntimeError(f"OpenTrashMail 未能解析随机邮箱: {preview}")

        self._log(f"[OpenTrashMail] 生成邮箱: {email}")
        return MailboxAccount(
            email=email,
            account_id=email,
            extra={"provider": "opentrashmail"},
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            return {
                str(message.get("id"))
                for message in self._list_messages(account.email)
                if message.get("id") is not None
            }
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
        import re

        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {
            str(code) for code in (kwargs.get("exclude_codes") or set()) if code
        }

        def poll_once() -> Optional[str]:
            try:
                messages = self._list_messages(account.email)
                for message in messages:
                    message_id = str(message.get("id") or "").strip()
                    if not message_id or message_id in seen:
                        continue
                    seen.add(message_id)

                    detail = self._get_message_detail(account.email, message_id)
                    parsed = detail.get("parsed") if isinstance(detail, dict) else {}
                    if not isinstance(parsed, dict):
                        parsed = {}

                    decoded_raw = self._decode_raw_content(detail.get("raw") or "")
                    search_text = " ".join(
                        [
                            str(message.get("subject") or ""),
                            str(message.get("from") or ""),
                            str(message.get("body") or ""),
                            str(detail.get("from") or ""),
                            str(parsed.get("subject") or ""),
                            str(parsed.get("body") or ""),
                            str(parsed.get("htmlbody") or ""),
                            decoded_raw,
                        ]
                    ).strip()
                    search_text = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                        "",
                        search_text,
                    )
                    if keyword and keyword.lower() not in search_text.lower():
                        continue

                    code = self._safe_extract(search_text, code_pattern)
                    if code and code in exclude_codes:
                        continue
                    if code:
                        self._log(f"[OpenTrashMail] 收到验证码: {code}")
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )

class CFRoutingMailbox(BaseMailbox):
    """Cloudflare 邮件路由（catch-all 转发 + IMAP 轮询）"""

    def __init__(
        self,
        domain: str = "",
        imap_server: str = "",
        imap_port: int | str = 993,
        username: str = "",
        password: str = "",
        mailboxes: str = "INBOX",
        poll_interval_seconds: float | str = 2,
        proxy: str = None,
    ):
        self.domains = self._parse_domains(domain)
        self.imap_server = str(imap_server or "").strip()
        try:
            self.imap_port = int(imap_port or 993)
        except (TypeError, ValueError):
            self.imap_port = 993
        self.username = str(username or "").strip()
        self.password = str(password or "").strip()
        self.mailboxes = self._normalize_mailboxes(mailboxes)
        self.poll_interval_seconds = self._normalize_poll_interval(
            poll_interval_seconds
        )
        # 当前 provider 只使用 IMAP，暂未对 IMAP 连接做代理封装；保留参数以兼容统一工厂。
        self.proxy = build_requests_proxy_config(proxy)

    @staticmethod
    def _normalize_domain(domain: Any) -> str:
        value = str(domain or "").strip().lower()
        if value.startswith("@"):
            value = value[1:]
        return value

    @classmethod
    def _parse_domains(cls, value: Any) -> list[str]:
        if not value:
            return []

        items: list[Any]
        if isinstance(value, (list, tuple, set)):
            items = list(value)
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                items = parsed
            else:
                items = [
                    part for chunk in text.splitlines() for part in chunk.split(",")
                ]
        else:
            items = [value]

        domains: list[str] = []
        seen = set()
        for item in items:
            domain = cls._normalize_domain(item)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            domains.append(domain)
        return domains

    @staticmethod
    def _normalize_mailboxes(value: Any) -> list[str]:
        if isinstance(value, (list, tuple, set)):
            items = [str(item or "").strip() for item in value]
        else:
            raw = str(value or "INBOX").strip() or "INBOX"
            items = [item.strip() for item in raw.split(",")]

        result = []
        seen = set()
        for item in items:
            if not item:
                continue
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            result.append(item)
        return result or ["INBOX"]

    @staticmethod
    def _normalize_poll_interval(value: Any) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            resolved = 2.0
        return max(resolved, 0.5)

    @staticmethod
    def _generate_local_part() -> str:
        import string

        prefix = "".join(random.choices(string.ascii_lowercase, k=6))
        suffix = "".join(random.choices(string.digits, k=4))
        return f"{prefix}{suffix}"

    def _ensure_configured(self) -> None:
        if not self.domains:
            raise RuntimeError(
                "Cloudflare 邮件路由未配置域名：请设置 cfrouting_domain"
            )
        if not self.imap_server:
            raise RuntimeError(
                "Cloudflare 邮件路由未配置 IMAP 服务器：请设置 cfrouting_imap_server"
            )
        if not self.username:
            raise RuntimeError(
                "Cloudflare 邮件路由未配置 IMAP 用户名：请设置 cfrouting_username"
            )
        if not self.password:
            raise RuntimeError(
                "Cloudflare 邮件路由未配置 IMAP 密码：请设置 cfrouting_password"
            )

    def _pick_domain(self) -> str:
        self._ensure_configured()
        return random.choice(self.domains)

    def get_email(self) -> MailboxAccount:
        domain = self._pick_domain()
        email = f"{self._generate_local_part()}@{domain}"
        self._log(f"[CFRouting] 本次使用邮箱: {email}")
        return MailboxAccount(
            email=email,
            account_id=email,
            extra={
                "provider": "cfrouting",
                "route_domain": domain,
                "imap_username": self.username,
            },
        )

    def _open_imap(self):
        import imaplib

        self._ensure_configured()
        conn = imaplib.IMAP4_SSL(self.imap_server, self.imap_port, timeout=30)
        conn.login(self.username, self.password)
        return conn

    def _select_mailbox(self, imap_conn, mailbox: str) -> bool:
        target = str(mailbox or "").strip() or "INBOX"
        try:
            status, _ = imap_conn.select(target, readonly=True)
            if status == "OK":
                return True
        except Exception:
            pass

        try:
            status, _ = imap_conn.select(f'"{target}"', readonly=True)
            return status == "OK"
        except Exception:
            return False

    def _decode_header_value(self, value: str) -> str:
        from email.header import decode_header

        if not value:
            return ""
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                try:
                    decoded.append(part.decode(charset or "utf-8", errors="ignore"))
                except Exception:
                    decoded.append(part.decode("utf-8", errors="ignore"))
            else:
                decoded.append(str(part))
        return "".join(decoded)

    def _extract_message_text(self, message) -> str:
        subject = self._decode_header_value(message.get("Subject", ""))
        body_chunks = []
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                content_type = part.get_content_type()
                if content_type not in ("text/plain", "text/html"):
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_chunks.append(payload.decode(charset, errors="ignore"))
                except Exception:
                    body_chunks.append(payload.decode("utf-8", errors="ignore"))
        else:
            payload = message.get_payload(decode=True)
            if payload is None:
                payload = message.get_payload()
            if isinstance(payload, bytes):
                try:
                    body_chunks.append(payload.decode("utf-8", errors="ignore"))
                except Exception:
                    body_chunks.append(payload.decode("latin1", errors="ignore"))
            elif payload:
                body_chunks.append(str(payload))

        combined = (subject + " " + " ".join(body_chunks)).strip()
        return self._decode_raw_content(combined)

    def _message_matches_alias(self, message, alias: str) -> bool:
        target = str(alias or "").strip().lower()
        if not target:
            return True

        fragments = []
        for header_name, value in message.items():
            decoded = self._decode_header_value(value)
            if decoded:
                fragments.append(f"{header_name}: {decoded}")

        haystack = "\n".join(fragments).lower()
        return (
            target in haystack
            or f"<{target}>" in haystack
            or f"for <{target}>" in haystack
        )

    def _fetch_recent_message_uids(self, imap_conn, mailbox: str) -> list[str]:
        if not self._select_mailbox(imap_conn, mailbox):
            return []

        status, data = imap_conn.uid("search", None, "ALL")
        if status != "OK":
            return []
        raw_ids = data[0].split() if data and data[0] else []
        if len(raw_ids) > 80:
            raw_ids = raw_ids[-80:]
        result = []
        for raw_uid in raw_ids:
            if isinstance(raw_uid, bytes):
                result.append(raw_uid.decode("utf-8", errors="ignore"))
            else:
                result.append(str(raw_uid))
        return [uid for uid in result if uid]

    @staticmethod
    def _supports_idle(imap_conn) -> bool:
        capabilities = getattr(imap_conn, "capabilities", ()) or ()
        normalized = set()
        for item in capabilities:
            if isinstance(item, bytes):
                normalized.add(item.decode("utf-8", errors="ignore").upper())
            else:
                normalized.add(str(item).upper())
        return "IDLE" in normalized

    @staticmethod
    def _clear_untagged_responses(imap_conn, *names: str) -> None:
        responses = getattr(imap_conn, "untagged_responses", None)
        if not isinstance(responses, dict):
            return
        for name in names:
            responses.pop(str(name or "").upper(), None)

    def _idle_wait_for_mailbox_event(
        self,
        imap_conn,
        mailbox: str,
        timeout: float,
    ) -> bool:
        import select

        idle_timeout = max(float(timeout or 0), 0.0)
        if idle_timeout <= 0 or not self._supports_idle(imap_conn):
            return False
        if not self._select_mailbox(imap_conn, mailbox):
            return False

        self._clear_untagged_responses(
            imap_conn,
            "EXISTS",
            "RECENT",
            "FETCH",
            "EXPUNGE",
        )

        tag = imap_conn._new_tag()
        idle_started = False
        try:
            imap_conn.send(tag + b" IDLE\r\n")
            idle_started = True
            continuation = imap_conn._get_response()
            if continuation is not None:
                return False

            deadline = time.monotonic() + idle_timeout
            while time.monotonic() < deadline:
                self._checkpoint()
                remaining = deadline - time.monotonic()
                wait_timeout = min(0.25, max(remaining, 0.0))
                if wait_timeout <= 0:
                    break

                sock = getattr(imap_conn, "sock", None)
                if sock is None:
                    break
                readable, _, _ = select.select([sock], [], [], wait_timeout)
                if not readable:
                    continue

                response = imap_conn._get_response()
                if response is None:
                    continue

                for name in ("EXISTS", "RECENT", "FETCH"):
                    if getattr(imap_conn, "untagged_responses", {}).get(name):
                        self._log(
                            "[CFRouting] IDLE 收到邮件事件: "
                            f"mailbox={mailbox} event={name}"
                        )
                        return True
            return False
        except Exception:
            return False
        finally:
            if idle_started:
                try:
                    imap_conn.send(b"DONE\r\n")
                    imap_conn._get_tagged_response(tag)
                except Exception:
                    pass

    def _scan_for_code(
        self,
        *,
        imap_conn,
        account: MailboxAccount,
        seen: set[str],
        keyword_lower: str,
        alias: str,
        code_pattern: str | None,
        exclude_codes: set[str],
    ) -> Optional[str]:
        from email import message_from_bytes
        from email.policy import default as email_default_policy

        fallback_candidates = []
        for mailbox in self.mailboxes:
            for uid in self._fetch_recent_message_uids(imap_conn, mailbox):
                message_id = f"{mailbox}:{uid}"
                if not uid or message_id in seen:
                    continue
                seen.add(message_id)

                status, msg_data = imap_conn.uid("fetch", uid, "(RFC822)")
                if status != "OK":
                    continue

                raw = None
                for item in msg_data or []:
                    if isinstance(item, tuple) and item[1]:
                        raw = item[1]
                        break
                if not raw:
                    continue

                message = message_from_bytes(raw, policy=email_default_policy)
                text = self._extract_message_text(message)
                text_lower = text.lower()
                alias_matched = self._message_matches_alias(message, alias)
                if not alias_matched and alias and alias in text_lower:
                    alias_matched = True

                if keyword_lower and keyword_lower not in text_lower:
                    continue

                code = self._safe_extract(text, code_pattern)
                if code and code in exclude_codes:
                    continue
                if not code:
                    continue
                if alias_matched:
                    self._log(
                        "[CFRouting] 命中验证码: "
                        f"alias={account.email} mailbox={mailbox} uid={uid} code={code}"
                    )
                    return code
                fallback_candidates.append(
                    {
                        "code": code,
                        "mailbox": mailbox,
                        "uid": uid,
                    }
                )

        if fallback_candidates:
            distinct_codes = {
                str(item.get("code") or "").strip()
                for item in fallback_candidates
                if str(item.get("code") or "").strip()
            }
            if len(distinct_codes) == 1:
                candidate = fallback_candidates[-1]
                code = str(candidate.get("code") or "").strip()
                self._log(
                    "[CFRouting] 邮件头未保留原始收件人，按新增邮件回退命中验证码: "
                    f"alias={account.email} mailbox={candidate.get('mailbox')} "
                    f"uid={candidate.get('uid')} code={code}"
                )
                return code
            self._log(
                "[CFRouting] 新增邮件里发现多个不同验证码，但都未命中原始收件人，"
                f"本轮跳过以避免误用: alias={account.email} count={len(fallback_candidates)}"
            )
        return None

    def get_current_ids(self, account: MailboxAccount) -> set:
        imap_conn = None
        try:
            imap_conn = self._open_imap()
            current_ids = set()
            for mailbox in self.mailboxes:
                for uid in self._fetch_recent_message_uids(imap_conn, mailbox):
                    current_ids.add(f"{mailbox}:{uid}")
            return current_ids
        except Exception:
            return set()
        finally:
            try:
                if imap_conn:
                    imap_conn.logout()
            except Exception:
                pass

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }
        keyword_lower = str(keyword or "").strip().lower()
        alias = str(account.email or "").strip().lower()
        timeout_seconds = max(int(timeout or 0), 1)
        deadline = time.monotonic() + timeout_seconds
        imap_conn = None
        try:
            imap_conn = self._open_imap()
            idle_enabled = self._supports_idle(imap_conn)
            self._log(
                "[CFRouting] 开始等待验证码: "
                f"alias={account.email} idle={'on' if idle_enabled else 'off'} "
                f"window={self.poll_interval_seconds}s"
            )

            while time.monotonic() < deadline:
                self._checkpoint()
                code = self._scan_for_code(
                    imap_conn=imap_conn,
                    account=account,
                    seen=seen,
                    keyword_lower=keyword_lower,
                    alias=alias,
                    code_pattern=code_pattern,
                    exclude_codes=exclude_codes,
                )
                if code:
                    return code

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                wait_window = min(self.poll_interval_seconds, remaining)
                if idle_enabled:
                    notified = False
                    for mailbox in self.mailboxes:
                        if self._idle_wait_for_mailbox_event(
                            imap_conn,
                            mailbox,
                            wait_window,
                        ):
                            notified = True
                            break
                    if not notified:
                        self._log(
                            "[CFRouting] IDLE 等待窗口内未收到事件，立即重扫"
                        )
                    continue

                self._sleep_with_checkpoint(wait_window)

            self._checkpoint()
            raise TimeoutError(f"Cloudflare 邮件路由等待验证码超时 ({timeout}s)")
        finally:
            try:
                if imap_conn:
                    imap_conn.logout()
            except Exception:
                pass


class CFWorkerMailbox(BaseMailbox):
    """Cloudflare Worker 自建临时邮箱服务"""

    def __init__(
        self,
        api_url: str,
        admin_token: str = "",
        domain: str = "",
        domain_override: str = "",
        domains: Any = None,
        enabled_domains: Any = None,
        subdomain: str = "",
        domain_level_count: Any = 2,
        random_subdomain: Any = False,
        random_name_subdomain: Any = False,
        fingerprint: str = "",
        custom_auth: str = "",
        proxy: str = None,
    ):
        self.api = api_url.rstrip("/")
        self.admin_token = admin_token
        self.domain = self._normalize_domain(domain)
        self.domain_override = self._normalize_domain(domain_override)
        self.domains = self._parse_domains(domains)
        raw_enabled_domains = self._parse_domains(enabled_domains)
        if self.domains:
            allowed = set(self.domains)
            self.enabled_domains = [d for d in raw_enabled_domains if d in allowed]
        else:
            self.enabled_domains = raw_enabled_domains
        self.subdomain = self._normalize_subdomain(subdomain)
        self.domain_level_count = self._parse_domain_level_count(domain_level_count)
        self.random_subdomain = self._to_bool(random_subdomain)
        self.random_name_subdomain = self._to_bool(random_name_subdomain)
        self.fingerprint = fingerprint
        self.custom_auth = custom_auth
        self.proxy = build_requests_proxy_config(proxy)
        self._token = None

    def _headers(self) -> dict:
        h = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "x-admin-auth": self.admin_token,
        }
        if self.fingerprint:
            h["x-fingerprint"] = self.fingerprint
        if self.custom_auth:
            h["x-custom-auth"] = self.custom_auth
        return h

    def _ensure_api_configured(self) -> None:
        if not self.api:
            raise RuntimeError("CF Worker API URL 未配置")

    def _read_json(self, response, action: str):
        try:
            return response.json()
        except Exception:
            body = (response.text or "").strip()
            snippet = body[:200] if body else "<empty>"
            raise RuntimeError(
                f"CF Worker {action} 返回非 JSON 响应: HTTP {response.status_code}, body={snippet}"
            )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        payload: Optional[dict] = None,
        timeout: int = 15,
    ):
        import requests

        url = f"{self.api}{path}"
        response = requests.request(
            method,
            url,
            params=params,
            json=payload,
            headers=self._headers(),
            proxies=self.proxy,
            timeout=timeout,
        )
        body = (response.text or "").strip()
        preview = body[:200] or "<empty>"

        if response.status_code >= 400:
            if "private site password" in body.lower():
                raise RuntimeError(
                    "CFWorker API 需要私有站点密码，请配置 cfworker_custom_auth"
                )
            raise RuntimeError(
                f"CFWorker API {path} 失败: HTTP {response.status_code} {preview}"
            )

        try:
            return response.json()
        except Exception as e:
            raise RuntimeError(
                f"CFWorker API {path} 返回非 JSON: HTTP {response.status_code} {preview}"
            ) from e

    def _generate_local_part(self) -> str:
        import string

        # 避免纯数字开头，提高邮箱格式“像真人”的程度
        prefix = "".join(random.choices(string.ascii_lowercase, k=6))
        suffix = "".join(random.choices(string.digits, k=4))
        return f"{prefix}{suffix}"

    @staticmethod
    def _normalize_domain(domain: Any) -> str:
        value = str(domain or "").strip().lower()
        if value.startswith("@"):
            value = value[1:]
        return value

    @staticmethod
    def _normalize_subdomain(value: Any) -> str:
        sub = str(value or "").strip().lower().strip(".")
        if sub.startswith("@"):
            sub = sub[1:]
        parts = [part for part in sub.split(".") if part]
        return ".".join(parts)

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_domain_level_count(value: Any) -> int:
        try:
            parsed = int(str(value or "").strip() or "2")
        except (TypeError, ValueError):
            return 2
        return parsed if parsed >= 2 else 2

    @classmethod
    def _parse_domains(cls, value: Any) -> list[str]:
        if not value:
            return []

        items: list[Any]
        if isinstance(value, (list, tuple, set)):
            items = list(value)
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                items = parsed
            else:
                items = [
                    part for chunk in text.splitlines() for part in chunk.split(",")
                ]
        else:
            items = [value]

        domains: list[str] = []
        seen = set()
        for item in items:
            domain = cls._normalize_domain(item)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            domains.append(domain)
        return domains

    def _pick_domain(self) -> str:
        if self.domain_override:
            return self.domain_override
        if self.enabled_domains:
            return random.choice(self.enabled_domains)
        return self.domain

    def _generate_subdomain_label(self, length: int = 6) -> str:
        import string

        alphabet = string.ascii_lowercase + string.digits
        return "".join(random.choices(alphabet, k=length))

    def _compose_domain(self, base_domain: str) -> str:
        domain = self._normalize_domain(base_domain)
        if not domain:
            return ""

        sub_parts: list[str] = []
        if self.random_name_subdomain:
            try:
                import random

                import names

                name_func = random.choice([names.get_first_name, names.get_last_name])
                sub_parts.append(name_func().lower().replace(" ", ""))
            except ImportError:
                sub_parts.append(self._generate_subdomain_label())
        elif self.random_subdomain:
            sub_parts.append(self._generate_subdomain_label())
        if self.subdomain:
            sub_parts.append(self.subdomain)

        base_level_count = len([part for part in domain.split(".") if part])
        expected_total_levels = max(self.domain_level_count, 2)
        missing_levels = max(expected_total_levels - (base_level_count + len(sub_parts)), 0)
        if missing_levels > 0:
            fillers = [self._generate_subdomain_label() for _ in range(missing_levels)]
            sub_parts = fillers + sub_parts

        if not sub_parts:
            return domain
        return f"{'.'.join(sub_parts)}.{domain}"

    def get_email(self) -> MailboxAccount:
        self._ensure_api_configured()
        name = self._generate_local_part()
        payload = {"enablePrefix": True, "name": name}
        selected_domain = self._compose_domain(self._pick_domain())
        if selected_domain:
            payload["domain"] = selected_domain
            self._log(f"[CFWorker] 本次使用域名: {selected_domain}")
        data = self._request_json(
            "POST", "/admin/new_address", payload=payload, timeout=15
        )
        email = data.get("email", data.get("address", ""))
        token = data.get("token", data.get("jwt", ""))
        if not email or not token:
            raise RuntimeError(
                f"CFWorker API /admin/new_address 返回缺少 email/jwt: {data}"
            )
        self._token = token
        print(
            f"[CFWorker] 生成邮箱: {email} token={token[:40] if token else 'NONE'}..."
        )
        return MailboxAccount(
            email=email,
            account_id=token,
            extra={"cfworker_domain": selected_domain} if selected_domain else None,
        )

    def _get_mails(self, email: str) -> list:
        self._ensure_api_configured()
        data = self._request_json(
            "GET",
            "/admin/mails",
            params={"limit": 20, "offset": 0, "address": email},
            timeout=10,
        )
        return data.get("results", data) if isinstance(data, dict) else data

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            mails = self._get_mails(account.email)
            return {str(m.get("id", "")) for m in mails}
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
        import re
        from datetime import datetime, timezone

        seen = set(before_ids or [])
        exclude_codes = set(kwargs.get("exclude_codes") or [])
        otp_sent_at = kwargs.get("otp_sent_at")
        otp_cutoff = float(otp_sent_at) - 2 if otp_sent_at else None

        def poll_once() -> Optional[str]:
            try:
                mails = self._get_mails(account.email)
                for mail in sorted(mails, key=lambda x: x.get("id", 0), reverse=True):
                    mid = str(mail.get("id", ""))
                    if not mid or mid in seen:
                        continue

                    created_at = str(mail.get("created_at", "") or "").strip()
                    if otp_cutoff and created_at:
                        try:
                            mail_ts = (
                                datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                                .replace(tzinfo=timezone.utc)
                                .timestamp()
                            )
                            if mail_ts < otp_cutoff:
                                self._log(
                                    f"[CFWorker] \u8df3\u8fc7\u65e7\u90ae\u4ef6 id={mid} created_at={created_at}"
                                )
                                continue
                        except Exception:
                            pass

                    # 仅在通过时间边界筛选后再标记为已处理，避免边界邮件被过早加入 seen。
                    seen.add(mid)

                    raw = str(mail.get("raw", ""))
                    subject = str(mail.get("subject", ""))
                    search_text = f"{subject} {self._decode_raw_content(raw)}".strip()
                    search_text = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                        "",
                        search_text,
                    )
                    search_text = re.sub(r"m=\+\d+\.\d+", "", search_text)
                    search_text = re.sub(r"\bt=\d+\b", "", search_text)
                    if keyword and keyword.lower() not in search_text.lower():
                        continue

                    code = self._safe_extract(search_text, code_pattern)
                    if code and code in exclude_codes:
                        self._log(
                            "[CFWorker] 跳过已用验证码 "
                            f"id={mid} created_at={created_at} code={code}"
                        )
                        continue
                    if code:
                        self._log(
                            "[CFWorker] 命中新验证码 "
                            f"id={mid} created_at={created_at} code={code}"
                        )
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
            timeout_message=f"\u7b49\u5f85\u9a8c\u8bc1\u7801\u8d85\u65f6 ({timeout}s)",
        )


class MoeMailMailbox(BaseMailbox):
    """MoeMail (sall.cc) 邮箱服务 - 自动注册账号并生成临时邮箱"""

    def __init__(
        self, api_url: str = "https://sall.cc", api_key: str = "", proxy: str = None
    ):
        self.api = api_url.rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.proxy = build_requests_proxy_config(proxy)
        self._session_token = None
        self._email = None

    def _api_headers(self) -> dict:
        if not self.api_key:
            return {}
        return {"X-API-Key": self.api_key}

    def _register_and_login(self) -> str:
        import string

        import requests

        s = requests.Session()
        s.proxies = self.proxy
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
        s.headers.update(
            {"user-agent": ua, "origin": self.api, "referer": f"{self.api}/zh-CN/login"}
        )
        s.headers.update(self._api_headers())
        # 注册
        username = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        password = "Test" + "".join(random.choices(string.digits, k=8)) + "!"
        print(f"[MoeMail] 注册账号: {username} / {password}")
        r_reg = s.post(
            f"{self.api}/api/auth/register",
            json={"username": username, "password": password, "turnstileToken": ""},
            timeout=15,
        )
        print(f"[MoeMail] 注册结果: {r_reg.status_code} {r_reg.text[:80]}")
        # 获取 CSRF
        csrf_r = s.get(f"{self.api}/api/auth/csrf", timeout=10)
        csrf = csrf_r.json().get("csrfToken", "")
        # 登录
        s.post(
            f"{self.api}/api/auth/callback/credentials",
            headers={"content-type": "application/x-www-form-urlencoded"},
            data=f"username={username}&password={password}&csrfToken={csrf}&redirect=false&callbackUrl={self.api}",
            allow_redirects=True,
            timeout=15,
        )
        self._session = s
        for cookie in s.cookies:
            if "session-token" in cookie.name:
                self._session_token = cookie.value
                print("[MoeMail] 登录成功")
                return cookie.value
        print(f"[MoeMail] 登录失败，cookies: {[c.name for c in s.cookies]}")
        return ""

    def get_email(self) -> MailboxAccount:
        # 每次调用都重新注册新账号，保证邮箱唯一
        self._session_token = None
        self._register_and_login()
        import string

        name = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        # 获取可用域名列表，随机选一个
        domain = "sall.cc"
        try:
            cfg_r = self._session.get(
                f"{self.api}/api/config", headers=self._api_headers(), timeout=10
            )
            domains = [
                d.strip()
                for d in cfg_r.json().get("emailDomains", "sall.cc").split(",")
                if d.strip()
            ]
            if domains:
                domain = random.choice(domains)
        except Exception:
            pass
        r = self._session.post(
            f"{self.api}/api/emails/generate",
            headers=self._api_headers(),
            json={"name": name, "domain": domain, "expiryTime": 86400000},
            timeout=15,
        )
        data = r.json()
        self._email = data.get("email", data.get("address", ""))
        email_id = data.get("id", "")
        print(
            f"[MoeMail] 生成邮箱: {self._email} id={email_id} domain={domain} status={r.status_code}"
        )
        if not email_id:
            print(f"[MoeMail] 生成失败: {data}")
        if email_id:
            self._email_count = getattr(self, "_email_count", 0) + 1
        return MailboxAccount(email=self._email, account_id=str(email_id))

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            r = self._session.get(
                f"{self.api}/api/emails/{account.account_id}",
                headers=self._api_headers(),
                timeout=10,
            )
            return {str(m.get("id", "")) for m in r.json().get("messages", [])}
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
        import re

        seen = set(before_ids or [])

        def poll_once() -> Optional[str]:
            try:
                r = self._session.get(
                    f"{self.api}/api/emails/{account.account_id}",
                    headers=self._api_headers(),
                    timeout=10,
                )
                msgs = r.json().get("messages", [])
                for msg in msgs:
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    body = (
                        str(
                            msg.get("content")
                            or msg.get("text")
                            or msg.get("body")
                            or msg.get("html")
                            or ""
                        )
                        + " "
                        + str(msg.get("subject") or "")
                    )
                    body = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "", body
                    )
                    code = self._safe_extract(body, code_pattern)
                    if code:
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class LuckMailMailbox(BaseMailbox):
    """LuckMail 混合模式：ChatGPT 走购买邮箱，其他平台走订单接码"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        project_code: str = "",
        email_type: str = "",
        domain: str = "",
        proxy: str = None,
    ):
        if not base_url or not api_key:
            raise RuntimeError(
                "LuckMail 未配置：请在全局设置中填写 luckmail_base_url 和 luckmail_api_key"
            )
        from .luckmail import LuckMailClient

        self._client = LuckMailClient(
            base_url=base_url,
            api_key=api_key,
            proxy_url=proxy,
        )
        self._project_code = project_code
        self._email_type = email_type or None
        self._domain = domain or None
        self._order_no = None
        self._token = None
        self._email = None

    def _use_purchase_mode(self, account: MailboxAccount = None) -> bool:
        if (
            account
            and account.account_id
            and str(account.account_id).startswith("tok_")
        ):
            return True
        if self._token:
            return True
        return self._project_code == "openai"

    def _resolve_token(self, account: MailboxAccount = None) -> str:
        token = (account.account_id if account else "") or self._token
        if token:
            self._token = token
            return token

        email = (account.email if account else "") or self._email
        if not email:
            return ""

        try:
            purchases = self._client.user.get_purchases(
                page=1,
                page_size=100,
                keyword=email,
            )
        except Exception:
            return ""

        email_lower = str(email).strip().lower()
        for item in purchases.list:
            if str(item.email_address).strip().lower() == email_lower and item.token:
                self._token = item.token
                self._email = item.email_address
                return item.token
        return ""

    def _cancel_order_silently(self, order_no: str) -> None:
        if not order_no:
            return
        try:
            self._client.user.cancel_order(order_no)
            self._log(f"[LuckMail] 已取消订单: {order_no}")
        except Exception:
            pass

    def _extract_code_from_token_mails(
        self,
        token: str,
        code_pattern: str = None,
        before_ids: set = None,
        exclude_codes: set = None,
    ) -> Optional[str]:
        try:
            mail_list = self._client.user.get_token_mails(token)
        except Exception:
            return None

        seen = {str(mid) for mid in (before_ids or set())}
        excluded = {str(code) for code in (exclude_codes or set()) if code}
        for mail in mail_list.mails:
            message_id = str(mail.message_id or "")
            if message_id and message_id in seen:
                continue
            body = " ".join(
                [
                    str(mail.subject or ""),
                    str(mail.body or ""),
                    str(mail.html_body or ""),
                ]
            )
            code = self._safe_extract(body, code_pattern)
            if code and code in excluded:
                continue
            if code:
                return code
        return None

    def get_email(self) -> MailboxAccount:
        if not self._project_code:
            raise RuntimeError("LuckMail 未设置 project_code，无法创建邮箱")

        if self._use_purchase_mode():
            self._log(
                f"[LuckMail] 分支: ChatGPT + LuckMail -> 购买邮箱接口 "
                f"(project_code={self._project_code}, "
                f"email_type={self._email_type or '-'}, domain={self._domain or '-'})"
            )
            try:
                result = self._client.user.purchase_emails(
                    project_code=self._project_code,
                    quantity=1,
                    email_type=self._email_type,
                    domain=self._domain,
                )
            except Exception as e:
                raise RuntimeError(f"LuckMail 购买邮箱失败: {e}") from e

            purchases = (result or {}).get("purchases") or []
            if not purchases:
                raise RuntimeError(f"LuckMail 购买邮箱返回为空: {result}")

            item = purchases[0]
            email = str(item.get("email_address") or "").strip()
            token = str(item.get("token") or "").strip()
            if not email or not token:
                raise RuntimeError(f"LuckMail 返回缺少 email/token: {item}")

            self._email = email
            self._token = token
            self._log(f"[LuckMail] 已购邮箱: {email}")
            if item.get("warranty_until"):
                self._log(f"[LuckMail] 质保到期: {item.get('warranty_until')}")
            return MailboxAccount(
                email=email,
                account_id=token,
                extra={
                    "provider": "luckmail",
                    "token": token,
                    "project_code": self._project_code,
                },
            )

        self._log(
            f"[LuckMail] 分支: 其他平台 + LuckMail -> 创建订单/订单接码 "
            f"(project_code={self._project_code}, email_type={self._email_type or '-'})"
        )
        try:
            body = {"project_code": self._project_code}
            if self._email_type:
                body["email_type"] = self._email_type
            order = self._client.user._sync_create_order(body)
        except Exception as e:
            raise RuntimeError(f"LuckMail 创建订单失败: {e}") from e
        self._order_no = order.order_no
        email = order.email_address
        self._email = email
        self._log(f"[LuckMail] 订单 {order.order_no} 分配邮箱: {email}")
        self._log(f"[LuckMail] 超时时间: {order.expired_at}")
        return MailboxAccount(email=email, account_id=order.order_no)

    def get_current_ids(self, account: MailboxAccount) -> set:
        if not self._use_purchase_mode(account):
            return set()
        token = self._resolve_token(account)
        if not token:
            return set()
        try:
            mail_list = self._client.user.get_token_mails(token)
            return {str(m.message_id) for m in (mail_list.mails or []) if m.message_id}
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
        if not self._use_purchase_mode(account):
            self._log("[LuckMail] 等验证码分支: 订单接码")
            order_no = account.account_id or self._order_no
            if not order_no:
                raise RuntimeError("LuckMail 未创建订单，无法等待验证码")

            def on_poll_order(result):
                self._log(f"[LuckMail] 轮询中... 状态: {result.status}")

            deadline = time.monotonic() + max(int(timeout or 0), 1)
            last_status = "pending"
            try:
                while time.monotonic() < deadline:
                    self._checkpoint()
                    remaining = max(1, int(deadline - time.monotonic()))
                    slice_timeout = min(remaining, 6)
                    try:
                        code_result = self._client.user._sync_wait_for_code(
                            order_no=order_no,
                            timeout=slice_timeout,
                            interval=3.0,
                            on_poll=on_poll_order,
                        )
                    except Exception as e:
                        raise TimeoutError(f"LuckMail 等待验证码失败: {e}") from e

                    last_status = str(code_result.status or "pending")
                    if code_result.status == "success" and code_result.verification_code:
                        code = code_result.verification_code
                        self._log(f"[LuckMail] 收到验证码: {code}")
                        return code
                    if code_result.status in {"cancelled", "timeout"}:
                        break
            except Exception:
                self._cancel_order_silently(order_no)
                raise

            self._cancel_order_silently(order_no)
            raise TimeoutError(
                f"LuckMail 等待验证码超时 ({timeout}s)，最终状态: {last_status}"
            )

        token = self._resolve_token(account)
        if not token:
            raise RuntimeError("LuckMail 未找到已购邮箱 Token，无法等待验证码")
        self._log("[LuckMail] 等验证码分支: 已购邮箱 Token 收码")

        exclude_codes = {
            str(code) for code in (kwargs.get("exclude_codes") or set()) if code
        }
        seen_message_ids = {str(mid) for mid in (before_ids or set()) if mid}
        if before_ids is None:
            seen_message_ids = self.get_current_ids(account)
            if seen_message_ids:
                self._log(
                    f"[LuckMail] 已建立旧邮件基线，先跳过 {len(seen_message_ids)} 封历史邮件"
                )

        saw_new_mail = False

        def poll_once() -> Optional[str]:
            nonlocal saw_new_mail
            found_new_mail = False
            try:
                mail_list = self._client.user.get_token_mails(token)
            except Exception as e:
                raise TimeoutError(f"LuckMail 等待验证码失败: {e}") from e

            for mail in mail_list.mails:
                message_id = str(mail.message_id or "").strip()
                if message_id and message_id in seen_message_ids:
                    continue

                found_new_mail = True
                saw_new_mail = True
                if message_id:
                    seen_message_ids.add(message_id)

                body = " ".join(
                    [
                        str(mail.subject or ""),
                        str(mail.body or ""),
                        str(mail.html_body or ""),
                    ]
                )
                code = self._safe_extract(body, code_pattern)
                if code and code in exclude_codes:
                    self._log(
                        f"[LuckMail] 跳过已使用验证码 message_id={message_id or '-'} code={code}"
                    )
                    continue
                if code:
                    self._log(f"[LuckMail] 收到验证码: {code}")
                    return code

            self._log(
                f"[LuckMail] 轮询中... 新邮件: {'是' if found_new_mail else '否'}"
            )

            if found_new_mail:
                self._log("[LuckMail] 新邮件还不是可用验证码，继续等下一封...")
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
            timeout_message=(
                f"LuckMail 等待验证码超时 ({timeout}s)，最终状态: "
                f"has_new_mail={saw_new_mail}"
            ),
        )


class OutlookMailboxBackend(ABC):
    """Outlook 收信后端策略。"""

    backend_name: str = ""

    def __init__(self, mailbox: "OutlookMailbox"):
        self.mailbox = mailbox

    @abstractmethod
    def get_current_ids(self, account: MailboxAccount) -> set:
        ...

    @abstractmethod
    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set | None = None,
        code_pattern: str | None = None,
        **kwargs,
    ) -> str:
        ...


class OutlookImapMailboxBackend(OutlookMailboxBackend):
    backend_name = "imap"

    def get_current_ids(self, account: MailboxAccount) -> set:
        imap_conn = None
        try:
            imap_conn = self.mailbox._open_imap(account)
            seen: set[str] = set()
            for folder in self.mailbox._imap_folder_names:
                status, _ = imap_conn.select(folder, readonly=True)
                if status != "OK":
                    continue
                status, data = imap_conn.uid("search", None, "ALL")
                if status != "OK":
                    continue
                ids = data[0].split() if data and data[0] else []
                for uid in ids[-100:]:
                    uid_str = (
                        uid.decode("utf-8", errors="ignore")
                        if isinstance(uid, bytes)
                        else str(uid)
                    )
                    if uid_str:
                        seen.add(f"{folder}:{uid_str}")
            return seen
        finally:
            try:
                if imap_conn:
                    imap_conn.logout()
            except Exception:
                pass

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set | None = None,
        code_pattern: str | None = None,
        **kwargs,
    ) -> str:
        from email import message_from_bytes
        from email.policy import default as email_default_policy

        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }
        keyword_lower = str(keyword or "").strip().lower()

        def poll_once() -> Optional[str]:
            for folder in self.mailbox._imap_folder_names:
                imap_conn = None
                try:
                    self.mailbox._log(f"[微软邮箱][IMAP] folder={folder} 开始轮询")
                    imap_conn = self.mailbox._open_imap(account)
                    self.mailbox._log(f"[微软邮箱][IMAP] folder={folder} IMAP 登录成功")
                    status, _ = imap_conn.select(folder, readonly=True)
                    if status != "OK":
                        self.mailbox._log(
                            f"[微软邮箱][IMAP] folder={folder} select 失败: status={status}"
                        )
                        continue
                    status, data = imap_conn.uid("search", None, "ALL")
                    if status != "OK":
                        self.mailbox._log(
                            f"[微软邮箱][IMAP] folder={folder} search 失败: status={status}"
                        )
                        continue
                    ids = data[0].split() if data and data[0] else []
                    if len(ids) > 50:
                        ids = ids[-50:]
                    new_uids = []
                    for uid in ids:
                        uid_str = (
                            uid.decode("utf-8", errors="ignore")
                            if isinstance(uid, bytes)
                            else str(uid)
                        )
                        seen_key = f"{folder}:{uid_str}"
                        if not uid_str or seen_key in seen:
                            continue
                        seen.add(seen_key)
                        new_uids.append(uid)
                    self.mailbox._log(
                        f"[微软邮箱][IMAP] folder={folder} uid_total={len(ids)} new_uid_count={len(new_uids)}"
                    )
                    for uid in new_uids:
                        status, msg_data = imap_conn.uid("fetch", uid, "(RFC822)")
                        if status != "OK":
                            self.mailbox._log(
                                f"[微软邮箱][IMAP] folder={folder} fetch 失败: uid={uid!r} status={status}"
                            )
                            continue
                        raw = None
                        for item in msg_data or []:
                            if isinstance(item, tuple) and item[1]:
                                raw = item[1]
                                break
                        if not raw:
                            self.mailbox._log(
                                f"[微软邮箱][IMAP] folder={folder} fetch 空响应: uid={uid!r}"
                            )
                            continue
                        msg = message_from_bytes(raw, policy=email_default_policy)
                        subject = self.mailbox._decode_header_value(msg.get("Subject", ""))
                        text = self.mailbox._extract_message_text(msg)
                        self.mailbox._log(
                            f"[微软邮箱][IMAP] folder={folder} 命中新邮件 subject={subject or '-'}"
                        )
                        if keyword_lower and keyword_lower not in text.lower():
                            self.mailbox._log(
                                f"[微软邮箱][IMAP] folder={folder} 跳过关键字不匹配邮件"
                            )
                            continue
                        code = self.mailbox._safe_extract(text, code_pattern)
                        if not code:
                            self.mailbox._log(
                                f"[微软邮箱][IMAP] folder={folder} 未提取到验证码"
                            )
                            continue
                        if code in exclude_codes:
                            self.mailbox._log(
                                f"[微软邮箱][IMAP] folder={folder} 跳过已尝试验证码: {code}"
                            )
                            continue
                        self.mailbox._log(
                            f"[微软邮箱][IMAP] folder={folder} 验证码提取成功: {code}"
                        )
                        return code
                except Exception as exc:
                    self.mailbox._log(
                        f"[微软邮箱][IMAP] folder={folder} IMAP 查询异常: {exc}"
                    )
                    continue
                finally:
                    try:
                        if imap_conn:
                            imap_conn.logout()
                    except Exception:
                        pass
            return None

        return self.mailbox._run_polling_wait(
            timeout=timeout,
            poll_interval=5,
            poll_once=poll_once,
        )


class OutlookGraphMailboxBackend(OutlookMailboxBackend):
    backend_name = "graph"

    def get_current_ids(self, account: MailboxAccount) -> set:
        access_token = self.mailbox._get_oauth_access_token(
            account,
            preferred_backend=self.backend_name,
        )
        seen: set[str] = set()
        for folder in self.mailbox._graph_folder_names:
            try:
                messages = self.mailbox._graph_list_messages(
                    access_token=access_token,
                    folder=folder,
                )
                for message in messages:
                    message_id = str(message.get("id") or "").strip()
                    if message_id:
                        seen.add(f"{folder}:{message_id}")
            except RuntimeError as exc:
                if "HTTP 401" in str(exc):
                    # 401 → token 失效，强制刷新后重试一次
                    self.mailbox._log(
                        f"[微软邮箱][Graph] get_current_ids folder={folder} 遇到 401，强制刷新 token"
                    )
                    _cache = (account.extra or {}).get("_oauth_token_cache")
                    if isinstance(_cache, dict):
                        _cache.pop(
                            self.mailbox._normalize_backend_name(self.backend_name), None
                        )
                    access_token = self.mailbox._get_oauth_access_token(
                        account,
                        preferred_backend=self.backend_name,
                    )
                    try:
                        messages = self.mailbox._graph_list_messages(
                            access_token=access_token,
                            folder=folder,
                        )
                        for message in messages:
                            message_id = str(message.get("id") or "").strip()
                            if message_id:
                                seen.add(f"{folder}:{message_id}")
                    except Exception:
                        pass
                else:
                    raise
        return seen

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set | None = None,
        code_pattern: str | None = None,
        **kwargs,
    ) -> str:
        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }
        keyword_lower = str(keyword or "").strip().lower()

        # 标记是否已做过一次 401 强制刷 token，避免无限循环
        _token_refreshed = False

        def _force_refresh_token() -> str:
            """清除 OAuth 缓存，强制重新获取 access token。"""
            _cache = (account.extra or {}).get("_oauth_token_cache")
            if isinstance(_cache, dict):
                _cache.pop(
                    self.mailbox._normalize_backend_name(self.backend_name), None
                )
            return self.mailbox._get_oauth_access_token(
                account,
                preferred_backend=self.backend_name,
            )

        def poll_once() -> Optional[str]:
            nonlocal _token_refreshed
            access_token = self.mailbox._get_oauth_access_token(
                account,
                preferred_backend=self.backend_name,
            )
            for folder in self.mailbox._graph_folder_names:
                try:
                    self.mailbox._log(f"[微软邮箱][Graph] folder={folder} 开始轮询")
                    messages = self.mailbox._graph_list_messages(
                        access_token=access_token,
                        folder=folder,
                    )
                    new_messages = []
                    for message in messages:
                        message_id = str(message.get("id") or "").strip()
                        seen_key = f"{folder}:{message_id}"
                        if not message_id or seen_key in seen:
                            continue
                        seen.add(seen_key)
                        new_messages.append(message)
                    self.mailbox._log(
                        f"[微软邮箱][Graph] folder={folder} message_total={len(messages)} new_count={len(new_messages)}"
                    )
                    for message in new_messages:
                        subject = str(message.get("subject") or "").strip()
                        text = self.mailbox._graph_message_text(message)
                        self.mailbox._log(
                            f"[微软邮箱][Graph] folder={folder} 命中新邮件 subject={subject or '-'}"
                        )
                        if keyword_lower and keyword_lower not in text.lower():
                            self.mailbox._log(
                                f"[微软邮箱][Graph] folder={folder} 跳过关键字不匹配邮件"
                            )
                            continue
                        code = self.mailbox._safe_extract(text, code_pattern)
                        if not code:
                            message_id = str(message.get("id") or "").strip()
                            if message_id:
                                detail = self.mailbox._graph_get_message(
                                    access_token=access_token,
                                    message_id=message_id,
                                )
                                text = self.mailbox._graph_message_text(detail)
                                code = self.mailbox._safe_extract(text, code_pattern)
                        if not code:
                            self.mailbox._log(
                                f"[微软邮箱][Graph] folder={folder} 未提取到验证码"
                            )
                            continue
                        if code in exclude_codes:
                            self.mailbox._log(
                                f"[微软邮箱][Graph] folder={folder} 跳过已尝试验证码: {code}"
                            )
                            continue
                        self.mailbox._log(
                            f"[微软邮箱][Graph] folder={folder} 验证码提取成功: {code}"
                        )
                        return code
                except Exception as exc:
                    exc_str = str(exc)
                    # 401 → token 失效，强制刷新后重试一次
                    if "HTTP 401" in exc_str and not _token_refreshed:
                        _token_refreshed = True
                        self.mailbox._log(
                            f"[微软邮箱][Graph] folder={folder} 遇到 401，强制刷新 token 后重试"
                        )
                        try:
                            access_token = _force_refresh_token()
                            messages = self.mailbox._graph_list_messages(
                                access_token=access_token,
                                folder=folder,
                            )
                            new_messages = []
                            for message in messages:
                                message_id = str(message.get("id") or "").strip()
                                seen_key = f"{folder}:{message_id}"
                                if not message_id or seen_key in seen:
                                    continue
                                seen.add(seen_key)
                                new_messages.append(message)
                            for message in new_messages:
                                subject = str(message.get("subject") or "").strip()
                                text = self.mailbox._graph_message_text(message)
                                if keyword_lower and keyword_lower not in text.lower():
                                    continue
                                code = self.mailbox._safe_extract(text, code_pattern)
                                if not code:
                                    mid = str(message.get("id") or "").strip()
                                    if mid:
                                        detail = self.mailbox._graph_get_message(
                                            access_token=access_token,
                                            message_id=mid,
                                        )
                                        text = self.mailbox._graph_message_text(detail)
                                        code = self.mailbox._safe_extract(text, code_pattern)
                                if code and code not in exclude_codes:
                                    self.mailbox._log(
                                        f"[微软邮箱][Graph] folder={folder} 刷新 token 后验证码提取成功: {code}"
                                    )
                                    return code
                        except Exception as retry_exc:
                            self.mailbox._log(
                                f"[微软邮箱][Graph] folder={folder} 刷新 token 后仍然失败: {retry_exc}"
                            )
                        continue
                    self.mailbox._log(
                        f"[微软邮箱][Graph] folder={folder} 查询异常: {exc}"
                    )
                    continue
            return None

        return self.mailbox._run_polling_wait(
            timeout=timeout,
            poll_interval=5,
            poll_once=poll_once,
        )


class MailApiUrlOtpBackend(OutlookMailboxBackend):
    backend_name = "mailapi_url"

    @staticmethod
    def _code_key(code: str) -> str:
        return f"mailapi_code:{str(code or '').strip()}"

    def _fetch_mailapi_text(self, account: MailboxAccount) -> str:
        import requests

        extra = account.extra or {}
        url = str(extra.get("mailapi_url") or "").strip()
        if not url:
            raise RuntimeError("mailapi_url 为空，无法轮询取码")
        response = requests.get(
            url,
            timeout=15,
            proxies=getattr(self.mailbox, "_proxy", None),
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"MailAPI 取码请求失败: HTTP {response.status_code}"
            )
        return str(response.text or "")

    def _extract_code(self, text: str, code_pattern: str | None) -> str:
        normalized_text = self.mailbox._decode_raw_content(text) or str(text or "")
        return str(self.mailbox._safe_extract(normalized_text, code_pattern) or "").strip()

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            text = self._fetch_mailapi_text(account)
            code = self._extract_code(text, None)
            return {self._code_key(code)} if code else set()
        except Exception:
            return set()

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set | None = None,
        code_pattern: str | None = None,
        **kwargs,
    ) -> str:
        seen = {str(mid) for mid in (before_ids or set())}
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }
        keyword_lower = str(keyword or "").strip().lower()

        def poll_once() -> Optional[str]:
            try:
                text = self._fetch_mailapi_text(account)
            except Exception as exc:
                self.mailbox._log(f"[MailAPI] 拉取失败: {exc}")
                return None

            if keyword_lower and keyword_lower not in str(text).lower():
                return None
            code = self._extract_code(text, code_pattern)
            if not code:
                return None
            if code in exclude_codes:
                self.mailbox._log(f"[MailAPI] 跳过已尝试验证码: {code}")
                return None
            code_key = self._code_key(code)
            if code_key in seen:
                return None
            seen.add(code_key)
            self.mailbox._log(f"[MailAPI] 收到验证码: {code}")
            return code

        return self.mailbox._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )


class OutlookMailbox(BaseMailbox):
    """微软邮箱（Outlook / Hotmail）本地账号池（Graph / IMAP 策略）"""

    # 类级别锁：保证多线程并发时取号互斥，防止多个实例取到同一个邮箱
    _pop_lock = threading.Lock()

    def __init__(
        self,
        imap_server: str = "",
        imap_port: int | str = 993,
        token_endpoint: str = "",
        backend: str = "graph",
        graph_api_base: str = "",
        proxy: str = None,
    ):
        self._lock = threading.Lock()
        self._proxy = build_requests_proxy_config(proxy)
        self._imap_servers = []
        if imap_server:
            self._imap_servers.append(str(imap_server).strip())
        else:
            try:
                from platforms.chatgpt.constants import OUTLOOK_IMAP_SERVERS

                self._imap_servers.extend(
                    [
                        str(OUTLOOK_IMAP_SERVERS.get("NEW") or "").strip(),
                        str(OUTLOOK_IMAP_SERVERS.get("OLD") or "").strip(),
                    ]
                )
            except Exception:
                self._imap_servers.extend(
                    ["outlook.live.com", "outlook.office365.com"]
                )
        self._imap_servers = [
            host for host in self._imap_servers if isinstance(host, str) and host
        ]
        try:
            self._imap_port = int(imap_port or 993)
        except (TypeError, ValueError):
            self._imap_port = 993
        self._token_endpoint = str(token_endpoint or "").strip()
        self._backend_name = self._normalize_backend_name(backend)
        self._graph_api_base = (
            str(graph_api_base or "").strip() or "https://graph.microsoft.com/v1.0"
        )
        self._imap_folder_names = ["INBOX", "Junk", "Deleted Items", "Trash"]
        self._graph_folder_names = ["inbox", "junkemail", "deleteditems"]
        self._backends: dict[str, OutlookMailboxBackend] = {
            "imap": OutlookImapMailboxBackend(self),
            "graph": OutlookGraphMailboxBackend(self),
            "mailapi_url": MailApiUrlOtpBackend(self),
        }

    @staticmethod
    def _normalize_backend_name(value: Any) -> str:
        backend = str(value or "graph").strip().lower() or "graph"
        return backend if backend in {"graph", "imap"} else "graph"

    @staticmethod
    def _normalize_account_type(value: Any) -> str:
        account_type = str(value or "").strip().lower()
        if account_type in {"mailapi_url", "microsoft_oauth"}:
            return account_type
        return "microsoft_oauth"

    def _is_mailapi_account(self, account: MailboxAccount) -> bool:
        extra = getattr(account, "extra", None) or {}
        account_type = self._normalize_account_type(extra.get("account_type"))
        if account_type == "mailapi_url":
            return True
        return bool(str(extra.get("mailapi_url") or "").strip())

    def _pop_account(self) -> dict:
        from sqlmodel import Session, select

        from core.db import OutlookAccountModel, engine

        with OutlookMailbox._pop_lock:
            with Session(engine) as session:
                account = (
                    session.exec(
                        select(OutlookAccountModel)
                        .where(OutlookAccountModel.enabled)
                        .order_by(OutlookAccountModel.id)
                    )
                    .first()
                )
                if not account:
                    raise RuntimeError("微软邮箱账号池为空，请先在设置页批量导入")

                payload = {
                    "id": account.id,
                    "email": account.email,
                    "password": account.password,
                    "client_id": account.client_id,
                    "refresh_token": account.refresh_token,
                    "account_type": getattr(account, "account_type", "microsoft_oauth"),
                    "mailapi_url": getattr(account, "mailapi_url", ""),
                }
                session.delete(account)
                session.commit()
                return payload

    def get_email(self) -> MailboxAccount:
        payload = self._pop_account()
        email = str(payload.get("email") or "").strip()
        if not email:
            raise RuntimeError("微软邮箱账号邮箱为空")
        password = str(payload.get("password") or "")
        client_id = str(payload.get("client_id") or "")
        refresh_token = str(payload.get("refresh_token") or "")
        account_type = self._normalize_account_type(payload.get("account_type"))
        mailapi_url = str(payload.get("mailapi_url") or "").strip()
        auth_mode = (
            "mailapi_url"
            if account_type == "mailapi_url"
            else ("oauth" if client_id and refresh_token else "password")
        )
        self._log(f"[微软邮箱] 取出账号: {email}（已从本地池移除）")
        self._log(
            "[微软邮箱] 账号认证信息: "
            f"has_password={bool(password)} "
            f"has_client_id={bool(client_id)} "
            f"has_refresh_token={bool(refresh_token)} "
            f"has_mailapi_url={bool(mailapi_url)} "
            f"account_type={account_type} "
            f"auth_mode={auth_mode}"
        )
        return MailboxAccount(
            email=email,
            account_id=str(payload.get("id") or ""),
            extra={
                "provider": "microsoft",
                "password": password,
                "client_id": client_id,
                "refresh_token": refresh_token,
                "account_type": account_type,
                "mailapi_url": mailapi_url,
                "outlook_backend": self._backend_name,
            },
        )

    def requeue_account(self, account: MailboxAccount) -> None:
        from sqlmodel import Session, select
        from core.db import engine, OutlookAccountModel

        email = str(getattr(account, "email", "") or "").strip()
        extra = getattr(account, "extra", None) or {}
        if not email:
            return

        password = str(extra.get("password") or "")
        client_id = str(extra.get("client_id") or "")
        refresh_token = str(extra.get("refresh_token") or "")
        account_type = self._normalize_account_type(extra.get("account_type"))
        mailapi_url = str(extra.get("mailapi_url") or "")

        with self._lock:
            with Session(engine) as session:
                existing = session.exec(
                    select(OutlookAccountModel).where(OutlookAccountModel.email == email)
                ).first()
                if existing:
                    existing.password = password
                    existing.client_id = client_id
                    existing.refresh_token = refresh_token
                    existing.account_type = account_type
                    existing.mailapi_url = mailapi_url
                    existing.enabled = True
                    existing.updated_at = _utcnow()
                    session.add(existing)
                else:
                    session.add(
                        OutlookAccountModel(
                            email=email,
                            password=password,
                            client_id=client_id,
                            refresh_token=refresh_token,
                            account_type=account_type,
                            mailapi_url=mailapi_url,
                            enabled=True,
                            created_at=_utcnow(),
                            updated_at=_utcnow(),
                        )
                    )
                session.commit()
        self._log(f"[微软邮箱] 账号已回退到本地池: {email}")

    def _token_endpoints(self) -> list[str]:
        if self._token_endpoint:
            return [self._token_endpoint]
        try:
            from platforms.chatgpt.constants import MICROSOFT_TOKEN_ENDPOINTS

            return [
                MICROSOFT_TOKEN_ENDPOINTS.get("CONSUMERS", ""),
                MICROSOFT_TOKEN_ENDPOINTS.get("LIVE", ""),
                MICROSOFT_TOKEN_ENDPOINTS.get("COMMON", ""),
            ]
        except Exception:
            return [
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                "https://login.live.com/oauth20_token.srf",
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            ]

    def _oauth_scope_candidates(
        self,
        preferred_backend: str | None = None,
    ) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        try:
            from platforms.chatgpt.constants import MICROSOFT_SCOPES

            scope_map = {
                "imap_new": str(MICROSOFT_SCOPES.get("IMAP_NEW") or "").strip(),
                "outlook_default": "https://outlook.office.com/.default offline_access",
                "graph_default": str(MICROSOFT_SCOPES.get("GRAPH_API") or "").strip(),
                "empty": "",
            }
        except Exception:
            scope_map = {
                "imap_new": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
                "outlook_default": "https://outlook.office.com/.default offline_access",
                "graph_default": "https://graph.microsoft.com/.default",
                "empty": "",
            }

        backend = self._normalize_backend_name(preferred_backend or self._backend_name)
        ordered_labels = (
            ["graph_default", "outlook_default", "imap_new", "empty"]
            if backend == "graph"
            else ["imap_new", "outlook_default", "graph_default", "empty"]
        )
        raw_candidates = [(label, scope_map.get(label, "")) for label in ordered_labels]

        seen = set()
        for label, scope in raw_candidates:
            key = (str(label or "").strip(), str(scope or "").strip())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(key)
        return candidates

    def probe_oauth_availability(
        self,
        *,
        email: str,
        client_id: str,
        refresh_token: str,
        preferred_backend: str | None = None,
    ) -> dict[str, Any]:
        if not client_id or not refresh_token:
            self._log(
                f"[微软邮箱] OAuth token 跳过: email={email} has_client_id={bool(client_id)} has_refresh_token={bool(refresh_token)}"
            )
            return {
                "ok": False,
                "reason": "missing_oauth_credentials",
                "message": "缺少 client_id 或 refresh_token，无法通过微软邮箱可用性检测",
            }

        import requests

        last_error = ""
        for endpoint in self._token_endpoints():
            endpoint = str(endpoint or "").strip()
            if not endpoint:
                continue
            for scope_label, scope in self._oauth_scope_candidates(preferred_backend):
                payload = {
                    "client_id": client_id,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }
                if scope:
                    payload["scope"] = scope
                try:
                    self._log(
                        "[微软邮箱] OAuth token 请求: "
                        f"email={email} endpoint={endpoint} scope_label={scope_label} has_scope={bool(scope)}"
                    )
                    resp = requests.post(
                        endpoint,
                        data=payload,
                        timeout=20,
                        proxies=self._proxy,
                    )
                    self._log(
                        "[微软邮箱] OAuth token 响应: "
                        f"email={email} endpoint={endpoint} scope_label={scope_label} status={resp.status_code}"
                    )
                except Exception as exc:
                    last_error = str(exc)
                    self._log(
                        "[微软邮箱] OAuth token 请求异常: "
                        f"email={email} endpoint={endpoint} scope_label={scope_label} error={exc}"
                    )
                    continue

                body_text = str(resp.text or "")[:500]
                if resp.status_code >= 400:
                    self._log(f"[微软邮箱] OAuth token 失败响应: {body_text[:200]}")
                    lowered = body_text.lower()
                    if "invalid_grant" in lowered and "service abuse mode" in lowered:
                        return {
                            "ok": False,
                            "reason": "service_abuse_mode",
                            "message": "微软邮箱可用性检测未通过，账号处于 service abuse mode",
                            "status_code": resp.status_code,
                            "endpoint": endpoint,
                            "scope_label": scope_label,
                        }
                    last_error = body_text or f"HTTP {resp.status_code}"
                    continue

                try:
                    data = resp.json() if resp.content else {}
                    access_token = str(data.get("access_token") or "").strip()
                    if access_token:
                        expires_in = data.get("expires_in")
                        try:
                            expires_in_value = max(int(expires_in or 0), 0)
                        except (TypeError, ValueError):
                            expires_in_value = 0
                        self._log(
                            f"[微软邮箱] OAuth access token 获取成功: {email} (scope_label={scope_label})"
                        )
                        return {
                            "ok": True,
                            "reason": "ok",
                            "message": "微软邮箱可用性检测通过",
                            "access_token": access_token,
                            "scope_label": scope_label,
                            "endpoint": endpoint,
                            "expires_in": expires_in_value,
                        }

                    self._log(
                        f"[微软邮箱] OAuth token 响应未包含 access_token: keys={sorted(list(data.keys()))[:10]}"
                    )
                    last_error = body_text or "OAuth 响应未包含 access_token"
                except Exception as exc:
                    last_error = body_text or str(exc) or "OAuth 响应解析失败"
                    self._log(
                        "[微软邮箱] OAuth token 响应解析异常: "
                        f"email={email} endpoint={endpoint} scope_label={scope_label} error={exc}"
                    )
                    continue

        return {
            "ok": False,
            "reason": "oauth_token_failed",
            "message": f"微软邮箱可用性检测未通过: {last_error or 'OAuth token 获取失败'}",
        }

    def _fetch_oauth_token_bundle(
        self,
        *,
        email: str,
        client_id: str,
        refresh_token: str,
        preferred_backend: str | None = None,
    ) -> dict[str, Any]:
        probe = self.probe_oauth_availability(
            email=email,
            client_id=client_id,
            refresh_token=refresh_token,
            preferred_backend=preferred_backend,
        )
        if probe.get("ok"):
            return {
                "access_token": str(probe.get("access_token") or ""),
                "scope_label": probe.get("scope_label", ""),
                "expires_in": probe.get("expires_in", 0),
                "endpoint": probe.get("endpoint", ""),
            }
        self._log(f"[微软邮箱] OAuth token 获取失败，回退密码登录: {email}")
        return {"reason": str(probe.get("reason") or "")}

    def _fetch_oauth_token(
        self,
        *,
        email: str,
        client_id: str,
        refresh_token: str,
        preferred_backend: str | None = None,
    ) -> str:
        bundle = self._fetch_oauth_token_bundle(
            email=email,
            client_id=client_id,
            refresh_token=refresh_token,
            preferred_backend=preferred_backend,
        )
        return str(bundle.get("access_token") or "").strip()

    def _get_oauth_access_token(
        self,
        account: MailboxAccount,
        *,
        preferred_backend: str | None = None,
    ) -> str:
        extra = account.extra or {}
        client_id = str(extra.get("client_id") or "").strip()
        refresh_token = str(extra.get("refresh_token") or "").strip()
        email_addr = str(account.email or "").strip()
        if not client_id or not refresh_token:
            raise RuntimeError("微软邮箱 OAuth 凭据缺失，无法获取 access token")

        cache = extra.setdefault("_oauth_token_cache", {})
        cache_key = self._normalize_backend_name(preferred_backend or self._backend_name)
        cached = cache.get(cache_key) if isinstance(cache, dict) else None
        now = time.time()
        if isinstance(cached, dict):
            access_token = str(cached.get("access_token") or "").strip()
            expires_at = float(cached.get("expires_at") or 0)
            if access_token and expires_at > now + 60:
                return access_token

        bundle = self._fetch_oauth_token_bundle(
            email=email_addr,
            client_id=client_id,
            refresh_token=refresh_token,
            preferred_backend=cache_key,
        )
        access_token = str(bundle.get("access_token") or "").strip()
        if not access_token:
            reason = bundle.get("reason", "")
            suffix = f" [{reason}]" if reason else ""
            raise RuntimeError(f"微软邮箱 OAuth access token 获取失败{suffix}")

        expires_in = bundle.get("expires_in")
        try:
            expires_in_value = max(int(expires_in or 0), 0)
        except (TypeError, ValueError):
            expires_in_value = 0
        if isinstance(cache, dict):
            cache[cache_key] = {
                "access_token": access_token,
                "expires_at": now + expires_in_value if expires_in_value else now + 300,
                "scope_label": bundle.get("scope_label", ""),
            }
        return access_token

    def _imap_auth_oauth(self, imap_conn, *, email: str, access_token: str) -> None:
        auth_string = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
        imap_conn.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8"))

    def _open_imap(self, account: MailboxAccount):
        import imaplib

        email_addr = str(account.email or "").strip()
        extra = account.extra or {}
        password = str(extra.get("password") or "").strip()
        client_id = str(extra.get("client_id") or "").strip()
        refresh_token = str(extra.get("refresh_token") or "").strip()

        access_token = ""
        if client_id and refresh_token:
            access_token = self._get_oauth_access_token(
                account,
                preferred_backend="imap",
            )

        last_error = None
        for host in self._imap_servers:
            if not host:
                continue
            if access_token:
                try:
                    imap_conn = imaplib.IMAP4_SSL(host, self._imap_port, timeout=30)
                    self._imap_auth_oauth(
                        imap_conn, email=email_addr, access_token=access_token
                    )
                    return imap_conn
                except Exception as exc:
                    last_error = exc
                    try:
                        imap_conn.logout()
                    except Exception:
                        pass
            if password:
                try:
                    imap_conn = imaplib.IMAP4_SSL(host, self._imap_port, timeout=30)
                    imap_conn.login(email_addr, password)
                    return imap_conn
                except Exception as exc:
                    last_error = exc
                    try:
                        imap_conn.logout()
                    except Exception:
                        pass

        raise RuntimeError(f"微软邮箱 IMAP 登录失败: {last_error}")

    def _resolve_backend(self, account: MailboxAccount) -> OutlookMailboxBackend:
        extra = account.extra or {}
        if self._is_mailapi_account(account):
            return self._backends["mailapi_url"]
        override = self._normalize_backend_name(
            extra.get("outlook_backend") or self._backend_name
        )
        if override == "graph":
            has_oauth = bool(
                str(extra.get("client_id") or "").strip()
                and str(extra.get("refresh_token") or "").strip()
            )
            if not has_oauth:
                self._log(
                    "[微软邮箱] Graph 后端需要 OAuth 凭据，当前账号缺少 client_id/refresh_token，自动切换 IMAP"
                )
                override = "imap"
        return self._backends.get(override) or self._backends["graph"]

    def _graph_headers(self, *, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Prefer": 'outlook.body-content-type="text"',
        }

    def _graph_request_json(
        self,
        *,
        method: str,
        path: str,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import requests

        url = f"{self._graph_api_base.rstrip('/')}/{path.lstrip('/')}"
        resp = requests.request(
            method,
            url,
            headers=self._graph_headers(access_token=access_token),
            params=params or None,
            timeout=20,
            proxies=self._proxy,
        )
        if resp.status_code >= 400:
            preview = (resp.text or "")[:300]
            raise RuntimeError(
                f"Outlook Graph 请求失败: HTTP {resp.status_code} {preview}"
            )
        return resp.json() if resp.content else {}

    def _graph_list_messages(
        self,
        *,
        access_token: str,
        folder: str,
    ) -> list[dict[str, Any]]:
        data = self._graph_request_json(
            method="GET",
            path=f"/me/mailFolders/{folder}/messages",
            access_token=access_token,
            params={
                "$top": "25",
                "$orderby": "receivedDateTime DESC",
                "$select": "id,subject,bodyPreview,body,receivedDateTime,from,internetMessageId",
            },
        )
        value = data.get("value") or []
        return value if isinstance(value, list) else []

    def _graph_get_message(
        self,
        *,
        access_token: str,
        message_id: str,
    ) -> dict[str, Any]:
        from urllib.parse import quote

        return self._graph_request_json(
            method="GET",
            path=f"/me/messages/{quote(str(message_id or '').strip(), safe='')}",
            access_token=access_token,
            params={
                "$select": "id,subject,bodyPreview,body,uniqueBody,receivedDateTime,from,internetMessageId",
            },
        )

    def _graph_message_text(self, message: dict[str, Any]) -> str:
        subject = str((message or {}).get("subject") or "").strip()
        preview = str((message or {}).get("bodyPreview") or "").strip()

        body = (message or {}).get("body") or {}
        body_content = (
            str(body.get("content") or "").strip() if isinstance(body, dict) else ""
        )
        unique_body = (message or {}).get("uniqueBody") or {}
        unique_body_content = (
            str(unique_body.get("content") or "").strip()
            if isinstance(unique_body, dict)
            else ""
        )
        combined = " ".join(
            part for part in [subject, preview, body_content, unique_body_content] if part
        )
        return self._decode_raw_content(combined)

    def _decode_header_value(self, value: str) -> str:
        from email.header import decode_header

        if not value:
            return ""
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                try:
                    decoded.append(part.decode(charset or "utf-8", errors="ignore"))
                except Exception:
                    decoded.append(part.decode("utf-8", errors="ignore"))
            else:
                decoded.append(str(part))
        return "".join(decoded)

    def _extract_message_text(self, message) -> str:
        subject = self._decode_header_value(message.get("Subject", ""))
        body_chunks = []
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                content_type = part.get_content_type()
                if content_type not in ("text/plain", "text/html"):
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_chunks.append(payload.decode(charset, errors="ignore"))
                except Exception:
                    body_chunks.append(payload.decode("utf-8", errors="ignore"))
        else:
            payload = message.get_payload(decode=True)
            if payload is None:
                payload = message.get_payload()
            if isinstance(payload, bytes):
                try:
                    body_chunks.append(payload.decode("utf-8", errors="ignore"))
                except Exception:
                    body_chunks.append(payload.decode("latin1", errors="ignore"))
            elif payload:
                body_chunks.append(str(payload))

        combined = (subject + " " + " ".join(body_chunks)).strip()
        return self._decode_raw_content(combined)

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            backend = self._resolve_backend(account)
            self._log(f"[微软邮箱] 当前收信后端: {backend.backend_name}")
            return backend.get_current_ids(account)
        except Exception as exc:
            self._log(f"[微软邮箱] 获取当前邮件 ID 失败: {exc}")
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
        backend = self._resolve_backend(account)
        self._log(f"[微软邮箱] OTP 收信后端: {backend.backend_name}")
        return backend.wait_for_code(
            account,
            keyword=keyword,
            timeout=timeout,
            before_ids=before_ids,
            code_pattern=code_pattern,
            **kwargs,
        )


class FreemailMailbox(BaseMailbox):
    """
    Freemail 自建邮箱服务（基于 Cloudflare Worker）
    项目: https://github.com/idinging/freemail
    支持管理员令牌或账号密码两种认证方式
    """

    def __init__(
        self,
        api_url: str,
        admin_token: str = "",
        username: str = "",
        password: str = "",
        domain: str = "",
        proxy: str = None,
    ):
        self.api = api_url.rstrip("/")
        self.admin_token = admin_token
        self.username = username
        self.password = password
        self.domain = str(domain or "").strip().lstrip("@")
        self.proxy = build_requests_proxy_config(proxy)
        self._session = None
        self._email = None
        self._domains = None

    def _get_session(self):
        import requests

        s = requests.Session()
        s.proxies = self.proxy
        if self.admin_token:
            s.headers.update({"Authorization": f"Bearer {self.admin_token}"})
        elif self.username and self.password:
            s.post(
                f"{self.api}/api/login",
                json={"username": self.username, "password": self.password},
                timeout=15,
            )
        self._session = s
        return s

    def get_email(self) -> MailboxAccount:
        if not self._session:
            self._get_session()

        target_domain = self.domain
        domain_index = 0
        if target_domain:
            domains = self._ensure_domains()
            if domains:
                lookup = str(target_domain).lower()
                for idx, domain in enumerate(domains):
                    if str(domain or "").strip().lower() == lookup:
                        domain_index = idx
                        break

        params = {"domainIndex": domain_index} if target_domain else {}
        r = self._session.get(f"{self.api}/api/generate", params=params, timeout=15)
        data = r.json()
        email = str(data.get("email", "") or "")
        if target_domain and email and "@" in email:
            actual_domain = email.split("@", 1)[1].strip().lower()
            if actual_domain != target_domain.lower():
                self._log(
                    f"[Freemail] 指定域名 {target_domain} 未命中，实际返回 {actual_domain}"
                )

        self._email = email
        print(f"[Freemail] 生成邮箱: {email}")
        return MailboxAccount(email=email, account_id=email)

    def _ensure_domains(self) -> list:
        if self._domains is not None:
            return self._domains
        self._domains = []
        if not self._session:
            self._get_session()
        try:
            r = self._session.get(f"{self.api}/api/domains", timeout=15)
            payload = r.json()
            normalized = []
            def _append_domain(value):
                domain = str(value or "").strip().lstrip("@")
                if domain and domain not in normalized:
                    normalized.append(domain)
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        _append_domain(
                            item.get("domain")
                            or item.get("name")
                            or item.get("value")
                        )
                    else:
                        _append_domain(item)
            elif isinstance(payload, dict):
                candidates = payload.get("domains") or payload.get("data") or []
                if isinstance(candidates, list):
                    for item in candidates:
                        if isinstance(item, dict):
                            _append_domain(
                                item.get("domain")
                                or item.get("name")
                                or item.get("value")
                            )
                        else:
                            _append_domain(item)
            self._domains = normalized
        except Exception:
            self._domains = []
        return self._domains

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            r = self._session.get(
                f"{self.api}/api/emails",
                params={"mailbox": account.email, "limit": 50},
                timeout=10,
            )
            return {str(m["id"]) for m in r.json() if "id" in m}
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
        seen = set(before_ids or [])
        exclude_codes = {
            str(code).strip()
            for code in (kwargs.get("exclude_codes") or set())
            if str(code or "").strip()
        }

        def poll_once() -> Optional[str]:
            try:
                r = self._session.get(
                    f"{self.api}/api/emails",
                    params={"mailbox": account.email, "limit": 20},
                    timeout=10,
                )
                for msg in r.json():
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    # 直接用 verification_code 字段
                    code = str(msg.get("verification_code") or "").strip()
                    if code and code != "None":
                        if code in exclude_codes:
                            continue
                        return code
                    # 兜底：从 preview 提取
                    text = (
                        str(msg.get("preview", "")) + " " + str(msg.get("subject", ""))
                    )
                    code = self._safe_extract(text, code_pattern)
                    if code:
                        if code in exclude_codes:
                            continue
                        return code
            except Exception:
                pass
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=3,
            poll_once=poll_once,
        )
