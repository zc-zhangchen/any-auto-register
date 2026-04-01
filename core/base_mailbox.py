"""邮箱池基类 - 抽象临时邮箱/收件服务"""

import json
import random

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any
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
        import quopri, html, re

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
            proxy=proxy,
        )
    elif provider == "moemail":
        return MoeMailMailbox(
            api_url=extra.get("moemail_api_url", "https://sall.cc"),
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
    elif provider == "cfworker":
        return CFWorkerMailbox(
            api_url=extra.get("cfworker_api_url", ""),
            admin_token=extra.get("cfworker_admin_token", ""),
            domain=extra.get("cfworker_domain", ""),
            domain_override=extra.get("cfworker_domain_override", ""),
            domains=extra.get("cfworker_domains", ""),
            enabled_domains=extra.get("cfworker_enabled_domains", ""),
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
        )
    else:  # laoudo
        return LaoudoMailbox(
            auth_token=extra.get("laoudo_auth", ""),
            email=extra.get("laoudo_email", ""),
            account_id=extra.get("laoudo_account_id", ""),
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
        keyword: str = "trae",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        import re, time
        from curl_cffi import requests as curl_requests

        seen = set(before_ids) if before_ids else set()
        start = time.time()
        h = {"authorization": self.auth, "user-agent": self._ua}
        while time.time() - start < timeout:
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
            time.sleep(4)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")


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
        keyword: str = "trae",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        import re, time, requests

        seen = set(before_ids) if before_ids else set()
        last_check = None
        start = time.time()
        while time.time() - start < timeout:
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
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")


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
        import re, time, requests

        seen = set(before_ids or [])
        otp_sent_at = kwargs.get("otp_sent_at")
        otp_cutoff = float(otp_sent_at) - 2 if otp_sent_at else None
        start = time.time()
        while time.time() - start < timeout:
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
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")


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
        import time

        target = account.account_id or account.email
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
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
            time.sleep(3)

        raise TimeoutError(f"等待验证码超时 ({timeout}s)")


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
        import random, string

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
        import re, time

        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
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
                        body = str(msg.get("subject") or "")
                    body = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "", body
                    )
                    code = self._safe_extract(body, code_pattern)
                    if code:
                        return code
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")


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
        import time

        self._ensure_api_key()
        seen = {str(mid) for mid in (before_ids or set())}
        start = time.time()
        while time.time() - start < timeout:
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
                    search_text = self._decode_raw_content(search_text) or search_text
                    search_text = re.sub(
                        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                        "",
                        search_text,
                    )
                    if keyword and keyword.lower() not in search_text.lower():
                        continue

                    code = self._safe_extract(search_text, code_pattern)
                    if code:
                        self._log(f"[MaliAPI] 收到验证码: {code}")
                        return code
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")


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
        params: dict | None = None,
        payload: dict | None = None,
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

    def get_email(self) -> MailboxAccount:
        self._ensure_api_configured()
        name = self._generate_local_part()
        payload = {"enablePrefix": True, "name": name}
        selected_domain = self._pick_domain()
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
        import time
        from datetime import datetime, timezone

        seen = set(before_ids or [])
        exclude_codes = set(kwargs.get("exclude_codes") or [])
        otp_sent_at = kwargs.get("otp_sent_at")
        otp_cutoff = float(otp_sent_at) - 2 if otp_sent_at else None
        start = time.time()
        while time.time() - start < timeout:
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
                            f"[CFWorker] \u8df3\u8fc7\u5df2\u7528\u9a8c\u8bc1\u7801 id={mid} created_at={created_at} code={code}"
                        )
                        continue
                    if code:
                        self._log(
                            f"[CFWorker] \u547d\u4e2d\u65b0\u9a8c\u8bc1\u7801 id={mid} created_at={created_at} code={code}"
                        )
                        return code
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"\u7b49\u5f85\u9a8c\u8bc1\u7801\u8d85\u65f6 ({timeout}s)")


class MoeMailMailbox(BaseMailbox):
    """MoeMail (sall.cc) 邮箱服务 - 自动注册账号并生成临时邮箱"""

    def __init__(self, api_url: str = "https://sall.cc", proxy: str = None):
        self.api = api_url.rstrip("/")
        self.proxy = build_requests_proxy_config(proxy)
        self._session_token = None
        self._email = None

    def _register_and_login(self) -> str:
        import requests, random, string

        s = requests.Session()
        s.proxies = self.proxy
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        s.headers.update(
            {"user-agent": ua, "origin": self.api, "referer": f"{self.api}/zh-CN/login"}
        )
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
                print(f"[MoeMail] 登录成功")
                return cookie.value
        print(f"[MoeMail] 登录失败，cookies: {[c.name for c in s.cookies]}")
        return ""

    def get_email(self) -> MailboxAccount:
        # 每次调用都重新注册新账号，保证邮箱唯一
        self._session_token = None
        self._register_and_login()
        import random, string

        name = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        # 获取可用域名列表，随机选一个
        domain = "sall.cc"
        try:
            cfg_r = self._session.get(f"{self.api}/api/config", timeout=10)
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
                f"{self.api}/api/emails/{account.account_id}", timeout=10
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
        import re, time

        seen = set(before_ids or [])
        start = time.time()
        pattern = re.compile(code_pattern) if code_pattern else None
        while time.time() - start < timeout:
            try:
                r = self._session.get(
                    f"{self.api}/api/emails/{account.account_id}", timeout=10
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
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")


class LuckMailMailbox(BaseMailbox):
    """LuckMail 混合模式：ChatGPT 走购买邮箱，其他平台走订单接码"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        project_code: str = "",
        email_type: str = "",
        domain: str = "",
    ):
        if not base_url or not api_key:
            raise RuntimeError(
                "LuckMail 未配置：请在全局设置中填写 luckmail_base_url 和 luckmail_api_key"
            )
        from .luckmail import LuckMailClient

        self._client = LuckMailClient(
            base_url=base_url,
            api_key=api_key,
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
                f"(project_code={self._project_code}, email_type={self._email_type or '-'}, domain={self._domain or '-'})"
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

            try:
                code_result = self._client.user._sync_wait_for_code(
                    order_no=order_no,
                    timeout=timeout,
                    interval=3.0,
                    on_poll=on_poll_order,
                )
            except Exception as e:
                raise TimeoutError(f"LuckMail 等待验证码失败: {e}") from e

            if code_result.status == "success" and code_result.verification_code:
                code = code_result.verification_code
                self._log(f"[LuckMail] 收到验证码: {code}")
                return code

            raise TimeoutError(
                f"LuckMail 等待验证码超时 ({timeout}s)，最终状态: {code_result.status}"
            )

        token = self._resolve_token(account)
        if not token:
            raise RuntimeError("LuckMail 未找到已购邮箱 Token，无法等待验证码")
        self._log("[LuckMail] 等验证码分支: 已购邮箱 Token 收码")

        exclude_codes = {
            str(code) for code in (kwargs.get("exclude_codes") or set()) if code
        }

        def on_poll(result):
            self._log(
                f"[LuckMail] 轮询中... 新邮件: {'是' if result.has_new_mail else '否'}"
            )

        try:
            code_result = self._client.user.wait_for_token_code(
                token=token,
                timeout=timeout,
                interval=3.0,
                on_poll=on_poll,
            )
        except Exception as e:
            raise TimeoutError(f"LuckMail 等待验证码失败: {e}") from e

        code = code_result.verification_code
        if code and code in exclude_codes:
            code = None
        if not code and code_result.mail:
            parsed_code = self._safe_extract(
                json.dumps(code_result.mail, ensure_ascii=False), code_pattern
            )
            if parsed_code and parsed_code not in exclude_codes:
                code = parsed_code
        if not code and (code_result.has_new_mail or before_ids is None):
            code = self._extract_code_from_token_mails(
                token,
                code_pattern,
                before_ids=before_ids,
                exclude_codes=exclude_codes,
            )

        if code:
            self._log(f"[LuckMail] 收到验证码: {code}")
            return code

        raise TimeoutError(
            f"LuckMail 等待验证码超时 ({timeout}s)，最终状态: has_new_mail={code_result.has_new_mail}"
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
        proxy: str = None,
    ):
        self.api = api_url.rstrip("/")
        self.admin_token = admin_token
        self.username = username
        self.password = password
        self.proxy = build_requests_proxy_config(proxy)
        self._session = None
        self._email = None

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
        import requests

        r = self._session.get(f"{self.api}/api/generate", timeout=15)
        data = r.json()
        email = data.get("email", "")
        self._email = email
        print(f"[Freemail] 生成邮箱: {email}")
        return MailboxAccount(email=email, account_id=email)

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
        import re, time

        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
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
                    code = str(msg.get("verification_code") or "")
                    if code and code != "None":
                        return code
                    # 兜底：从 preview 提取
                    text = (
                        str(msg.get("preview", "")) + " " + str(msg.get("subject", ""))
                    )
                    code = self._safe_extract(text, code_pattern)
                    if code:
                        return code
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")
