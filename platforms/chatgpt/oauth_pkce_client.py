"""
OAuth PKCE 注册客户端

完整实现 auth.openai.com 注册状态机 + 登录获取 Token 的全生命周期。
每个步骤封装为独立方法，调用方按编号依次调用即可完成整个注册流程。
"""

import json
import re
import time
import urllib.parse
from typing import Optional

from curl_cffi import requests as curl_requests
from core.proxy_utils import build_requests_proxy_config

from .oauth import (
    OAuthStart,
    _decode_jwt_segment,
    generate_oauth_url,
    submit_callback_url,
)

AUTH_BASE = "https://auth.openai.com"
SENTINEL_API = "https://sentinel.openai.com/backend-api/sentinel/req"
SENTINEL_REFERER = (
    "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6"
)
CLOUDFLARE_TRACE = "https://cloudflare.com/cdn-cgi/trace"


class OAuthPkceClient:
    """
    OAuth PKCE 注册客户端

    完整注册流程（12 步）：
      1.  检查 IP 地区
      2.  访问 OAuth 授权 URL，获取 oai-did Cookie
      3.  获取 Sentinel Token
      4.  提交邮箱 (authorize/continue)
      5.  提交密码 (user/register)
      6.  发送 OTP (email-otp/send)
      7.  验证 OTP (email-otp/validate)
      8.  创建账户 (create_account)
      9.  注册后重新 OAuth 登录
      10. 解析 workspace_id
      11. 选择 workspace
      12. 跟踪重定向链，交换 OAuth code → access_token
    """

    def __init__(self, proxy: Optional[str] = None, log_fn=None):
        self.proxy = proxy
        self._log = log_fn or (lambda msg: None)
        self._proxies = build_requests_proxy_config(self.proxy)

        # 主会话：贯穿整个注册 + 登录流程
        self.session = curl_requests.Session(
            proxies=self._proxies,
            impersonate="chrome",
        )

        self._device_id: Optional[str] = None
        self._sentinel: Optional[str] = None

    # ══════════════════════════════════════════════════════════════════
    # 内部方法：获取 Sentinel Token（极简模式）
    # ══════════════════════════════════════════════════════════════════

    def _fetch_sentinel_token(
        self, device_id: str, flow: str = "authorize_continue"
    ) -> str:
        """
        获取 Sentinel Token。

        使用独立连接（不复用 session cookie），请求体 p 字段留空，
        只取响应中的 token 字段拼装为 openai-sentinel-token header 值。

        Returns:
            JSON 格式的 sentinel token 字符串。
        """
        req_body = json.dumps({"p": "", "id": device_id, "flow": flow})

        resp = curl_requests.post(
            SENTINEL_API,
            headers={
                "origin": "https://sentinel.openai.com",
                "referer": SENTINEL_REFERER,
                "content-type": "text/plain;charset=UTF-8",
            },
            data=req_body,
            proxies=self._proxies,
            impersonate="chrome",
            timeout=15,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Sentinel 获取失败: HTTP {resp.status_code}")

        c_value = resp.json().get("token", "")
        if not c_value:
            raise RuntimeError("Sentinel 响应缺少 token 字段")

        return json.dumps(
            {
                "p": "",
                "t": "",
                "c": c_value,
                "id": device_id,
                "flow": flow,
            },
            separators=(",", ":"),
        )

    # ══════════════════════════════════════════════════════════════════
    # 步骤 1：检查 IP 地区
    # ══════════════════════════════════════════════════════════════════

    def check_ip_region(self) -> str:
        """检查当前 IP 地区，CN/HK 不支持。"""
        try:
            resp = self.session.get(CLOUDFLARE_TRACE, timeout=10)
            match = re.search(r"^loc=(.+)$", resp.text, re.MULTILINE)
            loc = match.group(1).strip() if match else "UNKNOWN"
            self._log(f"当前 IP 地区: {loc}")
            if loc in ("CN", "HK"):
                raise RuntimeError(f"IP 地区不支持: {loc}")
            return loc
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"IP 地区检查失败: {e}") from e

    # ══════════════════════════════════════════════════════════════════
    # 步骤 2：访问 OAuth 授权 URL，获取 oai-did Cookie
    # ══════════════════════════════════════════════════════════════════

    def init_oauth_session(self) -> OAuthStart:
        """生成 OAuth PKCE URL 并访问，建立 auth.openai.com 会话。"""
        oauth = generate_oauth_url()
        self._log("访问 OAuth 授权 URL...")
        self.session.get(oauth.auth_url, timeout=15)
        self._device_id = self.session.cookies.get("oai-did") or ""
        self._log(
            f"oai-did: {self._device_id[:16]}..."
            if self._device_id
            else "oai-did: (未获取到)"
        )
        return oauth

    # ══════════════════════════════════════════════════════════════════
    # 步骤 3：获取 Sentinel Token
    # ══════════════════════════════════════════════════════════════════

    def refresh_sentinel(self) -> str:
        """获取新的 Sentinel Token 并缓存。"""
        if not self._device_id:
            raise RuntimeError("尚未初始化 oai-did（请先调用 init_oauth_session）")
        self._sentinel = self._fetch_sentinel_token(self._device_id)
        self._log("Sentinel Token 已获取")
        return self._sentinel

    # ══════════════════════════════════════════════════════════════════
    # 步骤 4：提交邮箱
    # ══════════════════════════════════════════════════════════════════

    def submit_email(self, email: str) -> dict:
        """向 authorize/continue 提交邮箱，触发注册状态机。"""
        if not self._sentinel:
            raise RuntimeError("Sentinel Token 未初始化")

        payload = json.dumps(
            {
                "username": {"value": email, "kind": "email"},
                "screen_hint": "signup",
            }
        )
        self._log(f"提交邮箱: {email}")

        resp = self.session.post(
            f"{AUTH_BASE}/api/accounts/authorize/continue",
            headers={
                "referer": f"{AUTH_BASE}/create-account",
                "accept": "application/json",
                "content-type": "application/json",
                "openai-sentinel-token": self._sentinel,
            },
            data=payload,
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"提交邮箱失败: HTTP {resp.status_code} {resp.text[:300]}"
            )

        data = resp.json()
        self._log(f"邮箱提交成功")
        return data

    # ══════════════════════════════════════════════════════════════════
    # 步骤 5：提交密码
    # ══════════════════════════════════════════════════════════════════

    def submit_password(self, email: str, password: str) -> str:
        """向 user/register 提交密码，返回 continue_url。"""
        payload = json.dumps({"password": password, "username": email})
        self._log("提交密码...")

        resp = self.session.post(
            f"{AUTH_BASE}/api/accounts/user/register",
            headers={
                "referer": f"{AUTH_BASE}/create-account/password",
                "accept": "application/json",
                "content-type": "application/json",
                "openai-sentinel-token": self._sentinel or "",
            },
            data=payload,
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"提交密码失败: HTTP {resp.status_code} {resp.text[:300]}"
            )

        continue_url = resp.json().get("continue_url") or ""
        self._log(f"密码提交成功{', continue_url 已获取' if continue_url else ''}")
        return continue_url

    # ══════════════════════════════════════════════════════════════════
    # 步骤 6：发送 OTP
    # ══════════════════════════════════════════════════════════════════

    def send_otp(self, continue_url: str = "") -> bool:
        """触发发送邮箱验证码。"""
        url = continue_url or f"{AUTH_BASE}/api/accounts/email-otp/send"
        self._log(f"发送验证码: {url}")

        try:
            resp = self.session.post(
                url,
                headers={
                    "referer": f"{AUTH_BASE}/create-account/password",
                    "accept": "application/json",
                    "content-type": "application/json",
                    "openai-sentinel-token": self._sentinel or "",
                },
                timeout=30,
            )
            self._log(f"验证码发送状态: {resp.status_code}")
            return resp.status_code == 200
        except Exception as e:
            self._log(f"发送验证码异常（非致命）: {e}")
            return False

    # ══════════════════════════════════════════════════════════════════
    # 步骤 7：验证 OTP
    # ══════════════════════════════════════════════════════════════════

    def validate_otp(self, code: str) -> None:
        """提交邮箱验证码。"""
        self._log(f"验证 OTP: {code}")

        resp = self.session.post(
            f"{AUTH_BASE}/api/accounts/email-otp/validate",
            headers={
                "referer": f"{AUTH_BASE}/email-verification",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=json.dumps({"code": code}),
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"OTP 验证失败: HTTP {resp.status_code} {resp.text[:300]}"
            )
        self._log("OTP 验证通过")

    # ══════════════════════════════════════════════════════════════════
    # 步骤 8：创建账户
    # ══════════════════════════════════════════════════════════════════

    def create_account(self, name: str, birthdate: str) -> None:
        """提交姓名和生日完成账户创建。"""
        self._log(f"创建账户: {name} ({birthdate})")

        resp = self.session.post(
            f"{AUTH_BASE}/api/accounts/create_account",
            headers={
                "referer": f"{AUTH_BASE}/about-you",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=json.dumps({"name": name, "birthdate": birthdate}),
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"创建账户失败: HTTP {resp.status_code} {resp.text[:300]}"
            )
        self._log("账户创建成功")

    # ══════════════════════════════════════════════════════════════════
    # 步骤 9：注册后重新 OAuth 登录
    # ══════════════════════════════════════════════════════════════════

    def login_after_register(
        self, email: str, password: str, otp_code: str = ""
    ) -> OAuthStart:
        """
        注册完成后重走 OAuth 登录流程。

        注册阶段的 session 不含 workspace 信息，必须重新走一次
        OAuth 登录获取 oai-client-auth-session Cookie。

        Returns:
            登录阶段的 OAuthStart（含 code_verifier 等，用于步骤 12 Token 交换）。
        """
        self._log("=" * 40)
        self._log("开始 OAuth 登录（获取 workspace）...")

        # 9-1. 访问新 OAuth URL
        login_oauth = generate_oauth_url()
        self.session.get(login_oauth.auth_url, timeout=15)
        login_did = self.session.cookies.get("oai-did") or self._device_id or ""
        self._log(
            f"登录阶段 oai-did: {login_did[:16]}..."
            if login_did
            else "登录阶段 oai-did: (空)"
        )

        # 9-2. 获取登录阶段 Sentinel
        login_sentinel = self._fetch_sentinel_token(login_did)

        # 9-3. 提交邮箱（screen_hint=login）
        login_email_resp = self.session.post(
            f"{AUTH_BASE}/api/accounts/authorize/continue",
            headers={
                "referer": f"{AUTH_BASE}/sign-in",
                "accept": "application/json",
                "content-type": "application/json",
                "openai-sentinel-token": login_sentinel,
            },
            data=json.dumps(
                {
                    "username": {"value": email, "kind": "email"},
                    "screen_hint": "login",
                }
            ),
            timeout=30,
        )
        if login_email_resp.status_code != 200:
            raise RuntimeError(f"登录提交邮箱失败: HTTP {login_email_resp.status_code}")

        page_type = (login_email_resp.json().get("page") or {}).get("type", "")
        self._log(f"登录页面类型: {page_type}")

        # 9-4. 提交密码（login_password 页面）
        if "password" in page_type:
            self._log("提交密码...")
            pwd_resp = self.session.post(
                f"{AUTH_BASE}/api/accounts/password/verify",
                headers={
                    "referer": f"{AUTH_BASE}/log-in/password",
                    "accept": "application/json",
                    "content-type": "application/json",
                    "openai-sentinel-token": login_sentinel,
                },
                data=json.dumps({"password": password}),
                timeout=30,
            )
            if pwd_resp.status_code != 200:
                raise RuntimeError(f"登录密码验证失败: HTTP {pwd_resp.status_code}")
            page_type = (pwd_resp.json().get("page") or {}).get("type", "")
            self._log(f"密码验证后页面类型: {page_type}")

        # 9-5. 二次 OTP（复用注册阶段验证码）
        if "otp" in page_type or "verification" in page_type:
            if not otp_code:
                raise RuntimeError("登录需要二次 OTP 验证，但未提供验证码")
            self._log(f"提交登录二次验证码: {otp_code}")
            # 触发发信请求以满足后端状态机（可忽略报错）
            try:
                self.session.post(
                    f"{AUTH_BASE}/api/accounts/passwordless/send-otp",
                    headers={
                        "referer": f"{AUTH_BASE}/log-in/password",
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                    timeout=10,
                )
            except Exception:
                pass

            otp_resp = self.session.post(
                f"{AUTH_BASE}/api/accounts/email-otp/validate",
                headers={
                    "referer": f"{AUTH_BASE}/email-verification",
                    "accept": "application/json",
                    "content-type": "application/json",
                    "openai-sentinel-token": login_sentinel,
                },
                data=json.dumps({"code": otp_code}),
                timeout=30,
            )
            if otp_resp.status_code != 200:
                raise RuntimeError(
                    f"登录二次 OTP 失败: HTTP {otp_resp.status_code} {otp_resp.text[:200]}"
                )
            self._log("登录二次验证通过")

        self._log("OAuth 登录流程完成")
        return login_oauth

    # ══════════════════════════════════════════════════════════════════
    # 步骤 10：解析 workspace_id
    # ══════════════════════════════════════════════════════════════════

    def extract_workspace_id(self) -> str:
        """从 oai-client-auth-session Cookie（JWT）中解析 workspace_id。"""
        auth_cookie = self.session.cookies.get("oai-client-auth-session") or ""
        if not auth_cookie:
            raise RuntimeError("未找到 oai-client-auth-session Cookie")

        # JWT 段遍历（workspace 可能在第一段或第二段）
        segments = auth_cookie.split(".")
        for i in range(min(len(segments), 2)):
            data = _decode_jwt_segment(segments[i])
            workspaces = data.get("workspaces") or []
            if workspaces:
                wid = str((workspaces[0] or {}).get("id") or "").strip()
                if wid:
                    self._log(f"成功解析 workspace_id: {wid}")
                    return wid

        # 调试信息
        first_data = _decode_jwt_segment(segments[0]) if segments else {}
        self._log(f"Cookie 字段: {list(first_data.keys())}")
        raise RuntimeError("无法从 Cookie 中解析 workspace_id")

    # ══════════════════════════════════════════════════════════════════
    # 步骤 11：选择 workspace
    # ══════════════════════════════════════════════════════════════════

    def select_workspace(self, workspace_id: str) -> str:
        """选择 workspace，返回 continue_url。"""
        self._log(f"选择 workspace: {workspace_id}")

        resp = self.session.post(
            f"{AUTH_BASE}/api/accounts/workspace/select",
            headers={
                "referer": f"{AUTH_BASE}/sign-in-with-chatgpt/codex/consent",
                "content-type": "application/json",
            },
            data=json.dumps({"workspace_id": workspace_id}),
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"workspace/select 失败: HTTP {resp.status_code} {resp.text[:300]}"
            )

        continue_url = str((resp.json() or {}).get("continue_url") or "").strip()
        if not continue_url:
            raise RuntimeError("workspace/select 响应缺少 continue_url")
        self._log("workspace 选择成功，continue_url 已获取")
        return continue_url

    # ══════════════════════════════════════════════════════════════════
    # 步骤 12：跟踪重定向链，交换 OAuth code → access_token
    # ══════════════════════════════════════════════════════════════════

    def follow_redirects_and_exchange_token(
        self, continue_url: str, oauth_start: OAuthStart
    ) -> dict:
        """跟踪重定向链，捕获 code= 回调 URL，交换 access_token。"""
        current_url = continue_url

        for hop in range(8):
            resp = self.session.get(current_url, allow_redirects=False, timeout=15)
            location = resp.headers.get("Location") or ""

            if resp.status_code not in (301, 302, 303, 307, 308) or not location:
                break

            next_url = urllib.parse.urljoin(current_url, location)
            self._log(f"重定向 [{hop + 1}] → {next_url[:100]}...")

            if "code=" in next_url and "state=" in next_url:
                self._log("捕获到 OAuth 回调 URL，交换 Token...")
                token_json = submit_callback_url(
                    callback_url=next_url,
                    expected_state=oauth_start.state,
                    code_verifier=oauth_start.code_verifier,
                    redirect_uri=oauth_start.redirect_uri,
                    proxy_url=self.proxy,
                )
                return json.loads(token_json)

            current_url = next_url

        raise RuntimeError("未能在重定向链中捕获到 OAuth 回调 URL（含 code= 参数）")
