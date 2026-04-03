"""
OAuth 客户端模块 - 处理 Codex OAuth 登录流程
"""

import time
import secrets
from urllib.parse import urlparse, parse_qs
from core.proxy_utils import build_requests_proxy_config

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    import requests as curl_requests

from .phone_service import SMSToMePhoneService
from .utils import (
    FlowState,
    build_browser_headers,
    describe_flow_state,
    extract_flow_state,
    generate_datadog_trace,
    generate_pkce,
    normalize_flow_url,
    random_delay,
    seed_oai_device_cookie,
)
from .sentinel_token import build_sentinel_token


class OAuthClient:
    """OAuth 客户端 - 用于获取 Access Token 和 Refresh Token"""

    def __init__(self, config, proxy=None, verbose=True, browser_mode="protocol"):
        """
        初始化 OAuth 客户端

        Args:
            config: 配置字典
            proxy: 代理地址
            verbose: 是否输出详细日志
            browser_mode: protocol | headless | headed
        """
        self.config = dict(config or {})
        self.oauth_issuer = self.config.get("oauth_issuer", "https://auth.openai.com")
        self.oauth_client_id = self.config.get(
            "oauth_client_id", "app_EMoamEEZ73f0CkXaXp7hrann"
        )
        self.oauth_redirect_uri = self.config.get(
            "oauth_redirect_uri", "http://localhost:1455/auth/callback"
        )
        self.proxy = proxy
        self.verbose = verbose
        self.browser_mode = browser_mode or "protocol"
        self.last_error = ""

        # 创建 session
        self.session = curl_requests.Session()
        if self.proxy:
            self.session.proxies = build_requests_proxy_config(self.proxy)

    def _log(self, msg):
        """输出日志"""
        if self.verbose:
            print(f"  [OAuth] {msg}")

    def _set_error(self, message):
        self.last_error = str(message or "").strip()
        if self.last_error:
            self._log(self.last_error)

    def _browser_pause(self, low=0.15, high=0.4):
        """在 headed 模式下注入轻微延迟，模拟真实浏览器操作节奏。"""
        if self.browser_mode == "headed":
            random_delay(low, high)

    @staticmethod
    def _iter_text_fragments(value):
        if isinstance(value, str):
            text = value.strip()
            if text:
                yield text
            return
        if isinstance(value, dict):
            for item in value.values():
                yield from OAuthClient._iter_text_fragments(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                yield from OAuthClient._iter_text_fragments(item)

    @classmethod
    def _should_blacklist_phone_failure(cls, detail="", state: FlowState | None = None):
        fragments = [str(detail or "").strip()]
        if state is not None:
            fragments.extend(
                cls._iter_text_fragments(
                    {
                        "page_type": state.page_type,
                        "continue_url": state.continue_url,
                        "current_url": state.current_url,
                        "payload": state.payload,
                        "raw": state.raw,
                    }
                )
            )

        combined = " | ".join(fragment for fragment in fragments if fragment).lower()
        if not combined:
            return False

        non_blacklist_markers = (
            "whatsapp",
            "未收到短信验证码",
            "手机号验证码错误",
            "phone-otp/resend",
            "phone-otp/validate 异常",
            "phone-otp/validate 响应不是 json",
            "phone-otp/validate 失败",
            "timeout",
            "timed out",
            "network",
            "connection",
            "proxy",
            "ssl",
            "tls",
            "captcha",
            "too many phone",
            "too many phone numbers",
            "too many verification requests",
            "验证请求过多",
            "接受短信次数过多",
            "session limit",
            "rate limit",
        )
        if any(marker in combined for marker in non_blacklist_markers):
            return False

        blacklist_markers = (
            "phone number is invalid",
            "invalid phone number",
            "invalid phone",
            "phone number invalid",
            "sms verification failed",
            "send sms verification failed",
            "unable to send sms",
            "not a valid mobile number",
            "unsupported phone number",
            "phone number not supported",
            "carrier not supported",
            "电话号码无效",
            "手机号无效",
            "发送短信验证失败",
            "号码无效",
            "号码不支持",
            "手机号不支持",
        )
        return any(marker in combined for marker in blacklist_markers)

    def _blacklist_phone_if_needed(
        self, phone_service, entry, detail="", state: FlowState | None = None
    ):
        if not entry or not self._should_blacklist_phone_failure(detail, state):
            return False
        try:
            phone_service.mark_blacklisted(entry.phone)
            self._log(f"已将手机号加入黑名单: {entry.phone}")
            return True
        except Exception as e:
            self._log(f"写入手机号黑名单失败: {e}")
            return False

    def _headers(
        self,
        url,
        *,
        user_agent=None,
        sec_ch_ua=None,
        accept,
        referer=None,
        origin=None,
        content_type=None,
        navigation=False,
        fetch_mode=None,
        fetch_dest=None,
        fetch_site=None,
        extra_headers=None,
    ):
        accept_language = None
        try:
            accept_language = self.session.headers.get("Accept-Language")
        except Exception:
            accept_language = None

        return build_browser_headers(
            url=url,
            user_agent=user_agent or "Mozilla/5.0",
            sec_ch_ua=sec_ch_ua,
            accept=accept,
            accept_language=accept_language or "en-US,en;q=0.9",
            referer=referer,
            origin=origin,
            content_type=content_type,
            navigation=navigation,
            fetch_mode=fetch_mode,
            fetch_dest=fetch_dest,
            fetch_site=fetch_site,
            headed=self.browser_mode == "headed",
            extra_headers=extra_headers,
        )

    def _state_from_url(self, url, method="GET"):
        state = extract_flow_state(
            current_url=normalize_flow_url(url, auth_base=self.oauth_issuer),
            auth_base=self.oauth_issuer,
            default_method=method,
        )
        if method:
            state.method = str(method).upper()
        return state

    def _state_from_payload(self, data, current_url=""):
        return extract_flow_state(
            data=data,
            current_url=current_url,
            auth_base=self.oauth_issuer,
        )

    def _state_signature(self, state: FlowState):
        return (
            state.page_type or "",
            state.method or "",
            state.continue_url or "",
            state.current_url or "",
        )

    def _extract_code_from_state(self, state: FlowState):
        for candidate in (
            state.continue_url,
            state.current_url,
            (state.payload or {}).get("url", ""),
        ):
            code = self._extract_code_from_url(candidate)
            if code:
                return code
        return None

    def _state_is_login_password(self, state: FlowState):
        return state.page_type == "login_password"

    def _state_is_email_otp(self, state: FlowState):
        target = f"{state.continue_url} {state.current_url}".lower()
        return (
            state.page_type == "email_otp_verification"
            or "email-verification" in target
            or "email-otp" in target
        )

    def _state_is_add_phone(self, state: FlowState):
        target = f"{state.continue_url} {state.current_url}".lower()
        return state.page_type == "add_phone" or "add-phone" in target

    def _state_requires_navigation(self, state: FlowState):
        method = (state.method or "GET").upper()
        if method != "GET":
            return False
        if (
            state.source == "api"
            and state.current_url
            and state.page_type not in {"login_password", "email_otp_verification"}
        ):
            return True
        if state.page_type == "external_url" and state.continue_url:
            return True
        if state.continue_url and state.continue_url != state.current_url:
            return True
        return False

    def _state_supports_workspace_resolution(self, state: FlowState):
        target = f"{state.continue_url} {state.current_url}".lower()
        if state.page_type in {
            "consent",
            "workspace_selection",
            "organization_selection",
        }:
            return True
        if any(
            marker in target
            for marker in (
                "sign-in-with-chatgpt",
                "consent",
                "workspace",
                "organization",
            )
        ):
            return True
        session_data = self._decode_oauth_session_cookie() or {}
        return bool(session_data.get("workspaces"))

    def _follow_flow_state(
        self,
        state: FlowState,
        referer=None,
        user_agent=None,
        impersonate=None,
        max_hops=16,
    ):
        """跟随服务端返回的 continue_url / current_url，返回新的状态或 authorization code。"""
        import re

        current_url = state.continue_url or state.current_url
        last_url = current_url or ""
        referer_url = referer

        if not current_url:
            return None, state

        initial_code = self._extract_code_from_url(current_url)
        if initial_code:
            return initial_code, self._state_from_url(current_url)

        for hop in range(max_hops):
            try:
                headers = self._headers(
                    current_url,
                    user_agent=user_agent,
                    accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    referer=referer_url,
                    navigation=True,
                )
                kwargs = {"headers": headers, "allow_redirects": False, "timeout": 30}
                if impersonate:
                    kwargs["impersonate"] = impersonate

                self._browser_pause(0.12, 0.3)
                r = self.session.get(current_url, **kwargs)
                last_url = str(r.url)
                self._log(f"follow[{hop + 1}] {r.status_code} {last_url[:120]}")
            except Exception as e:
                maybe_localhost = re.search(r"(https?://localhost[^\s\'\"]+)", str(e))
                if maybe_localhost:
                    location = maybe_localhost.group(1)
                    code = self._extract_code_from_url(location)
                    if code:
                        self._log("从 localhost 异常提取到 authorization code")
                        return code, self._state_from_url(location)
                self._log(f"follow[{hop + 1}] 异常: {str(e)[:160]}")
                return None, self._state_from_url(last_url or current_url)

            code = self._extract_code_from_url(last_url)
            if code:
                return code, self._state_from_url(last_url)

            if r.status_code in (301, 302, 303, 307, 308):
                location = normalize_flow_url(
                    r.headers.get("Location", ""), auth_base=self.oauth_issuer
                )
                if not location:
                    return None, self._state_from_url(last_url or current_url)
                code = self._extract_code_from_url(location)
                if code:
                    return code, self._state_from_url(location)
                referer_url = last_url or referer_url
                current_url = location
                continue

            content_type = (r.headers.get("content-type", "") or "").lower()
            if "application/json" in content_type:
                try:
                    next_state = self._state_from_payload(
                        r.json(), current_url=last_url or current_url
                    )
                except Exception:
                    next_state = self._state_from_url(last_url or current_url)
            else:
                next_state = self._state_from_url(last_url or current_url)

            return None, next_state

        return None, self._state_from_url(last_url or current_url)

    def _bootstrap_oauth_session(
        self,
        authorize_url,
        authorize_params,
        device_id=None,
        user_agent=None,
        sec_ch_ua=None,
        impersonate=None,
    ):
        """启动 OAuth 会话，确保 auth 域上的 login_session 已建立。"""
        if device_id:
            seed_oai_device_cookie(self.session, device_id)

        has_login_session = False
        authorize_final_url = ""

        try:
            headers = self._headers(
                authorize_url,
                user_agent=user_agent,
                sec_ch_ua=sec_ch_ua,
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                referer="https://chatgpt.com/",
                navigation=True,
            )
            kwargs = {
                "params": authorize_params,
                "headers": headers,
                "allow_redirects": True,
                "timeout": 30,
            }
            if impersonate:
                kwargs["impersonate"] = impersonate

            self._browser_pause()
            r = self.session.get(authorize_url, **kwargs)
            authorize_final_url = str(r.url)
            redirects = len(getattr(r, "history", []) or [])
            self._log(f"/oauth/authorize -> {r.status_code}, redirects={redirects}")

            has_login_session = any(
                (cookie.name if hasattr(cookie, "name") else str(cookie))
                == "login_session"
                for cookie in self.session.cookies
            )
            self._log(f"login_session: {'已获取' if has_login_session else '未获取'}")
        except Exception as e:
            self._log(f"/oauth/authorize 异常: {e}")

        if has_login_session:
            return authorize_final_url

        self._log("未获取到 login_session，尝试 /api/oauth/oauth2/auth...")
        try:
            oauth2_url = f"{self.oauth_issuer}/api/oauth/oauth2/auth"
            kwargs = {
                "params": authorize_params,
                "headers": self._headers(
                    oauth2_url,
                    user_agent=user_agent,
                    sec_ch_ua=sec_ch_ua,
                    accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    referer="https://chatgpt.com/",
                    navigation=True,
                ),
                "allow_redirects": True,
                "timeout": 30,
            }
            if impersonate:
                kwargs["impersonate"] = impersonate

            self._browser_pause()
            r2 = self.session.get(oauth2_url, **kwargs)
            authorize_final_url = str(r2.url)
            redirects2 = len(getattr(r2, "history", []) or [])
            self._log(
                f"/api/oauth/oauth2/auth -> {r2.status_code}, redirects={redirects2}"
            )

            has_login_session = any(
                (cookie.name if hasattr(cookie, "name") else str(cookie))
                == "login_session"
                for cookie in self.session.cookies
            )
            self._log(
                f"login_session(重试): {'已获取' if has_login_session else '未获取'}"
            )
        except Exception as e:
            self._log(f"/api/oauth/oauth2/auth 异常: {e}")

        return authorize_final_url

    def _submit_authorize_continue(
        self,
        email,
        device_id,
        continue_referer,
        *,
        user_agent=None,
        sec_ch_ua=None,
        impersonate=None,
        authorize_url=None,
        authorize_params=None,
    ):
        """提交邮箱，获取 OAuth 流程的第一页状态。"""
        self._log("步骤2: POST /api/accounts/authorize/continue")

        sentinel_token = build_sentinel_token(
            self.session,
            device_id,
            flow="authorize_continue",
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            impersonate=impersonate,
        )
        if not sentinel_token:
            self._set_error("无法获取 sentinel token (authorize_continue)")
            return None

        request_url = f"{self.oauth_issuer}/api/accounts/authorize/continue"
        headers = self._headers(
            request_url,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            accept="application/json",
            referer=continue_referer,
            origin=self.oauth_issuer,
            content_type="application/json",
            fetch_site="same-origin",
            extra_headers={
                "oai-device-id": device_id,
                "openai-sentinel-token": sentinel_token,
            },
        )
        headers.update(generate_datadog_trace())
        payload = {"username": {"kind": "email", "value": email}}

        try:
            kwargs = {
                "json": payload,
                "headers": headers,
                "timeout": 30,
                "allow_redirects": False,
            }
            if impersonate:
                kwargs["impersonate"] = impersonate

            self._browser_pause()
            r = self.session.post(request_url, **kwargs)
            self._log(f"/authorize/continue -> {r.status_code}")

            if (
                r.status_code == 400
                and "invalid_auth_step" in (r.text or "")
                and authorize_url
                and authorize_params
            ):
                self._log("invalid_auth_step，重新 bootstrap...")
                authorize_final_url = self._bootstrap_oauth_session(
                    authorize_url,
                    authorize_params,
                    device_id=device_id,
                    user_agent=user_agent,
                    sec_ch_ua=sec_ch_ua,
                    impersonate=impersonate,
                )
                continue_referer = (
                    authorize_final_url
                    if authorize_final_url.startswith(self.oauth_issuer)
                    else f"{self.oauth_issuer}/log-in"
                )
                headers["Referer"] = continue_referer
                headers["Sec-Fetch-Site"] = "same-origin"
                headers.update(generate_datadog_trace())
                kwargs = {
                    "json": payload,
                    "headers": headers,
                    "timeout": 30,
                    "allow_redirects": False,
                }
                if impersonate:
                    kwargs["impersonate"] = impersonate
                self._browser_pause()
                r = self.session.post(request_url, **kwargs)
                self._log(f"/authorize/continue(重试) -> {r.status_code}")

            if r.status_code != 200:
                self._set_error(f"提交邮箱失败: {r.status_code} - {r.text[:180]}")
                return None

            data = r.json()
            flow_state = self._state_from_payload(
                data, current_url=str(r.url) or request_url
            )
            self._log(describe_flow_state(flow_state))
            return flow_state
        except Exception as e:
            self._set_error(f"提交邮箱异常: {e}")
            return None

    def _submit_password_verify(
        self,
        password,
        device_id,
        *,
        user_agent=None,
        sec_ch_ua=None,
        impersonate=None,
        referer=None,
    ):
        """提交密码，获取下一步状态。"""
        self._log("步骤3: POST /api/accounts/password/verify")

        sentinel_pwd = build_sentinel_token(
            self.session,
            device_id,
            flow="password_verify",
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            impersonate=impersonate,
        )
        if not sentinel_pwd:
            self._set_error("无法获取 sentinel token (password_verify)")
            return None

        request_url = f"{self.oauth_issuer}/api/accounts/password/verify"
        headers = self._headers(
            request_url,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            accept="application/json",
            referer=referer or f"{self.oauth_issuer}/log-in/password",
            origin=self.oauth_issuer,
            content_type="application/json",
            fetch_site="same-origin",
            extra_headers={
                "oai-device-id": device_id,
                "openai-sentinel-token": sentinel_pwd,
            },
        )
        headers.update(generate_datadog_trace())

        try:
            kwargs = {
                "json": {"password": password},
                "headers": headers,
                "timeout": 30,
                "allow_redirects": False,
            }
            if impersonate:
                kwargs["impersonate"] = impersonate

            self._browser_pause()
            r = self.session.post(request_url, **kwargs)
            self._log(f"/password/verify -> {r.status_code}")

            if r.status_code != 200:
                self._set_error(f"密码验证失败: {r.status_code} - {r.text[:180]}")
                return None

            data = r.json()
            flow_state = self._state_from_payload(
                data, current_url=str(r.url) or request_url
            )
            self._log(f"verify {describe_flow_state(flow_state)}")
            return flow_state
        except Exception as e:
            self._set_error(f"密码验证异常: {e}")
            return None

    def login_and_get_tokens(
        self,
        email,
        password,
        device_id,
        user_agent=None,
        sec_ch_ua=None,
        impersonate=None,
        skymail_client=None,
    ):
        """
        完整的 OAuth 登录流程，获取 tokens

        Args:
            email: 邮箱
            password: 密码
            device_id: 设备 ID
            user_agent: User-Agent
            sec_ch_ua: sec-ch-ua header
            impersonate: curl_cffi impersonate 参数
            skymail_client: Skymail 客户端（用于获取 OTP，如果需要）

        Returns:
            dict: tokens 字典，包含 access_token, refresh_token, id_token
        """
        self.last_error = ""
        self._log("开始 OAuth 登录流程...")

        code_verifier, code_challenge = generate_pkce()
        oauth_state = secrets.token_urlsafe(32)
        authorize_params = {
            "response_type": "code",
            "client_id": self.oauth_client_id,
            "redirect_uri": self.oauth_redirect_uri,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": oauth_state,
        }
        authorize_url = f"{self.oauth_issuer}/oauth/authorize"

        seed_oai_device_cookie(self.session, device_id)

        self._log("步骤1: Bootstrap OAuth session...")
        authorize_final_url = self._bootstrap_oauth_session(
            authorize_url,
            authorize_params,
            device_id=device_id,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            impersonate=impersonate,
        )
        if not authorize_final_url:
            self._set_error("Bootstrap 失败")
            return None

        continue_referer = (
            authorize_final_url
            if authorize_final_url.startswith(self.oauth_issuer)
            else f"{self.oauth_issuer}/log-in"
        )

        state = self._submit_authorize_continue(
            email,
            device_id,
            continue_referer,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            impersonate=impersonate,
            authorize_url=authorize_url,
            authorize_params=authorize_params,
        )
        if not state:
            if not self.last_error:
                self._set_error("提交邮箱后未进入有效的 OAuth 状态")
            return None

        self._log(f"OAuth 状态起点: {describe_flow_state(state)}")
        seen_states = {}
        referer = continue_referer

        for step in range(20):
            signature = self._state_signature(state)
            seen_states[signature] = seen_states.get(signature, 0) + 1
            if seen_states[signature] > 2:
                self._set_error(f"OAuth 状态卡住: {describe_flow_state(state)}")
                return None

            code = self._extract_code_from_state(state)
            if code:
                self._log(f"获取到 authorization code: {code[:20]}...")
                self._log("步骤7: POST /oauth/token")
                tokens = self._exchange_code_for_tokens(
                    code, code_verifier, user_agent, impersonate
                )
                if tokens:
                    self._log("✅ OAuth 登录成功")
                else:
                    self._log("换取 tokens 失败")
                return tokens

            if self._state_is_login_password(state):
                next_state = self._submit_password_verify(
                    password,
                    device_id,
                    user_agent=user_agent,
                    sec_ch_ua=sec_ch_ua,
                    impersonate=impersonate,
                    referer=state.current_url or state.continue_url or referer,
                )
                if not next_state:
                    if not self.last_error:
                        self._set_error("密码验证后未进入下一步 OAuth 状态")
                    return None
                referer = state.current_url or referer
                state = next_state
                continue

            if self._state_is_email_otp(state):
                if not skymail_client:
                    self._set_error("当前流程需要邮箱 OTP，但缺少接码客户端")
                    return None
                next_state = self._handle_otp_verification(
                    email,
                    device_id,
                    user_agent,
                    sec_ch_ua,
                    impersonate,
                    skymail_client,
                    state,
                )
                if not next_state:
                    if not self.last_error:
                        self._set_error("邮箱 OTP 验证后未进入下一步 OAuth 状态")
                    return None
                referer = state.current_url or referer
                state = next_state
                continue

            if self._state_is_add_phone(state):
                next_state = self._handle_add_phone_verification(
                    device_id,
                    user_agent,
                    sec_ch_ua,
                    impersonate,
                    state,
                )
                if not next_state:
                    if not self.last_error:
                        self._set_error("手机号验证后未进入下一步 OAuth 状态")
                    return None
                referer = state.current_url or referer
                state = next_state
                continue

            if self._state_requires_navigation(state):
                code, next_state = self._follow_flow_state(
                    state,
                    referer=referer,
                    user_agent=user_agent,
                    impersonate=impersonate,
                )
                if code:
                    self._log(f"获取到 authorization code: {code[:20]}...")
                    self._log("步骤7: POST /oauth/token")
                    tokens = self._exchange_code_for_tokens(
                        code, code_verifier, user_agent, impersonate
                    )
                    if tokens:
                        self._log("✅ OAuth 登录成功")
                    else:
                        self._log("换取 tokens 失败")
                    return tokens
                referer = state.current_url or referer
                state = next_state
                self._log(f"follow state -> {describe_flow_state(state)}")
                continue

            if self._state_supports_workspace_resolution(state):
                self._log("步骤6: 执行 workspace/org 选择")
                code, next_state = self._oauth_submit_workspace_and_org(
                    state.continue_url
                    or state.current_url
                    or f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent",
                    device_id,
                    user_agent,
                    impersonate,
                )
                if code:
                    self._log(f"获取到 authorization code: {code[:20]}...")
                    self._log("步骤7: POST /oauth/token")
                    tokens = self._exchange_code_for_tokens(
                        code, code_verifier, user_agent, impersonate
                    )
                    if tokens:
                        self._log("✅ OAuth 登录成功")
                    else:
                        self._log("换取 tokens 失败")
                    return tokens
                if next_state:
                    referer = state.current_url or referer
                    state = next_state
                    self._log(f"workspace state -> {describe_flow_state(state)}")
                    continue

                if not self.last_error:
                    self._set_error(
                        f"workspace/org 选择失败: {describe_flow_state(state)}"
                    )
                return None

            self._set_error(f"未支持的 OAuth 状态: {describe_flow_state(state)}")
            return None

        self._set_error("OAuth 状态机超出最大步数")
        return None

    def _extract_code_from_url(self, url):
        """从 URL 中提取 code"""
        if not url or "code=" not in url:
            return None
        try:
            return parse_qs(urlparse(url).query).get("code", [None])[0]
        except Exception:
            return None

    def _oauth_follow_for_code(
        self, start_url, referer, user_agent, impersonate, max_hops=16
    ):
        """跟随 URL 获取 authorization code（手动跟随重定向）"""
        code, next_state = self._follow_flow_state(
            self._state_from_url(start_url),
            referer=referer,
            user_agent=user_agent,
            impersonate=impersonate,
            max_hops=max_hops,
        )
        return code, (next_state.current_url or next_state.continue_url or start_url)

    def _oauth_submit_workspace_and_org(
        self, consent_url, device_id, user_agent, impersonate, max_retries=3
    ):
        """提交 workspace 和 organization 选择（带重试）"""
        session_data = None

        for attempt in range(max_retries):
            session_data = self._load_workspace_session_data(
                consent_url=consent_url,
                user_agent=user_agent,
                impersonate=impersonate,
            )
            if session_data:
                break

            if attempt < max_retries - 1:
                self._log(
                    f"无法获取 consent session 数据 (尝试 {attempt + 1}/{max_retries})"
                )
                time.sleep(0.3)
            else:
                self._set_error("无法获取 consent session 数据")
                return None, None

        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            self._set_error("session 中没有 workspace 信息")
            return None, None

        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            self._set_error("workspace_id 为空")
            return None, None

        self._log(f"选择 workspace: {workspace_id}")

        headers = self._headers(
            f"{self.oauth_issuer}/api/accounts/workspace/select",
            user_agent=user_agent,
            accept="application/json",
            referer=consent_url,
            origin=self.oauth_issuer,
            content_type="application/json",
            fetch_site="same-origin",
            extra_headers={
                "oai-device-id": device_id,
            },
        )
        headers.update(generate_datadog_trace())

        try:
            kwargs = {
                "json": {"workspace_id": workspace_id},
                "headers": headers,
                "allow_redirects": False,
                "timeout": 30,
            }
            if impersonate:
                kwargs["impersonate"] = impersonate

            self._browser_pause()
            r = self.session.post(
                f"{self.oauth_issuer}/api/accounts/workspace/select", **kwargs
            )

            self._log(f"workspace/select -> {r.status_code}")

            # 检查重定向
            if r.status_code in (301, 302, 303, 307, 308):
                location = normalize_flow_url(
                    r.headers.get("Location", ""), auth_base=self.oauth_issuer
                )
                if "code=" in location:
                    code = self._extract_code_from_url(location)
                    if code:
                        self._log("从 workspace/select 重定向获取到 code")
                        return code, self._state_from_url(location)
                if location:
                    return None, self._state_from_url(location)

            # 如果返回 200，检查响应中的 orgs
            if r.status_code == 200:
                try:
                    data = r.json()
                    orgs = data.get("data", {}).get("orgs", [])
                    workspace_state = self._state_from_payload(
                        data, current_url=str(r.url)
                    )
                    continue_url = workspace_state.continue_url

                    if orgs:
                        org_id = (orgs[0] or {}).get("id")
                        projects = (orgs[0] or {}).get("projects", [])
                        project_id = (projects[0] or {}).get("id") if projects else None

                        if org_id:
                            self._log(f"选择 organization: {org_id}")

                            org_body = {"org_id": org_id}
                            if project_id:
                                org_body["project_id"] = project_id

                            org_referer = (
                                continue_url
                                if continue_url and continue_url.startswith("http")
                                else consent_url
                            )
                            headers = self._headers(
                                f"{self.oauth_issuer}/api/accounts/organization/select",
                                user_agent=user_agent,
                                accept="application/json",
                                referer=org_referer,
                                origin=self.oauth_issuer,
                                content_type="application/json",
                                fetch_site="same-origin",
                                extra_headers={
                                    "oai-device-id": device_id,
                                },
                            )
                            headers.update(generate_datadog_trace())

                            kwargs = {
                                "json": org_body,
                                "headers": headers,
                                "allow_redirects": False,
                                "timeout": 30,
                            }
                            if impersonate:
                                kwargs["impersonate"] = impersonate

                            self._browser_pause()
                            r_org = self.session.post(
                                f"{self.oauth_issuer}/api/accounts/organization/select",
                                **kwargs,
                            )

                            self._log(f"organization/select -> {r_org.status_code}")

                            # 检查重定向
                            if r_org.status_code in (301, 302, 303, 307, 308):
                                location = normalize_flow_url(
                                    r_org.headers.get("Location", ""),
                                    auth_base=self.oauth_issuer,
                                )
                                if "code=" in location:
                                    code = self._extract_code_from_url(location)
                                    if code:
                                        self._log(
                                            "从 organization/select 重定向获取到 code"
                                        )
                                        return code, self._state_from_url(location)
                                if location:
                                    return None, self._state_from_url(location)

                            # 检查 continue_url
                            if r_org.status_code == 200:
                                try:
                                    org_state = self._state_from_payload(
                                        r_org.json(), current_url=str(r_org.url)
                                    )
                                    self._log(
                                        f"organization/select -> {describe_flow_state(org_state)}"
                                    )
                                    if self._extract_code_from_state(org_state):
                                        return self._extract_code_from_state(
                                            org_state
                                        ), org_state
                                    return None, org_state
                                except Exception as e:
                                    self._set_error(
                                        f"解析 organization/select 响应异常: {e}"
                                    )

                    # 如果有 continue_url，跟随它
                    if continue_url:
                        code, _ = self._oauth_follow_for_code(
                            continue_url, consent_url, user_agent, impersonate
                        )
                        if code:
                            return code, self._state_from_url(continue_url)
                    return None, workspace_state

                except Exception as e:
                    self._set_error(f"处理 workspace/select 响应异常: {e}")
                    return None, None

        except Exception as e:
            self._set_error(f"workspace/select 异常: {e}")
            return None, None

        return None, None

    def _load_workspace_session_data(self, consent_url, user_agent, impersonate):
        """优先从 cookie 解码 session，失败时回退到 consent HTML 中提取 workspace 数据。"""
        session_data = self._decode_oauth_session_cookie()
        if session_data and session_data.get("workspaces"):
            return session_data

        html = self._fetch_consent_page_html(consent_url, user_agent, impersonate)
        if not html:
            return session_data

        parsed = self._extract_session_data_from_consent_html(html)
        if parsed and parsed.get("workspaces"):
            self._log(
                f"从 consent HTML 提取到 {len(parsed.get('workspaces', []))} 个 workspace"
            )
            return parsed

        return session_data

    def _fetch_consent_page_html(self, consent_url, user_agent, impersonate):
        """获取 consent 页 HTML，用于解析 React Router stream 中的 session 数据。"""
        try:
            headers = self._headers(
                consent_url,
                user_agent=user_agent,
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                referer=f"{self.oauth_issuer}/email-verification",
                navigation=True,
            )
            kwargs = {"headers": headers, "allow_redirects": False, "timeout": 30}
            if impersonate:
                kwargs["impersonate"] = impersonate
            self._browser_pause(0.12, 0.3)
            r = self.session.get(consent_url, **kwargs)
            if r.status_code == 200 and "text/html" in (
                r.headers.get("content-type", "").lower()
            ):
                return r.text
        except Exception:
            pass
        return ""

    def _extract_session_data_from_consent_html(self, html):
        """从 consent HTML 的 React Router stream 中提取 workspace session 数据。"""
        import json
        import re

        if not html or "workspaces" not in html:
            return None

        def _first_match(patterns, text):
            for pattern in patterns:
                m = re.search(pattern, text, re.S)
                if m:
                    return m.group(1)
            return ""

        def _build_from_text(text):
            if not text or "workspaces" not in text:
                return None

            normalized = text.replace('\\"', '"')

            session_id = _first_match(
                [
                    r'"session_id","([^"]+)"',
                    r'"session_id":"([^"]+)"',
                ],
                normalized,
            )
            client_id = _first_match(
                [
                    r'"openai_client_id","([^"]+)"',
                    r'"openai_client_id":"([^"]+)"',
                ],
                normalized,
            )

            start = normalized.find('"workspaces"')
            if start < 0:
                start = normalized.find("workspaces")
            if start < 0:
                return None

            end = normalized.find('"openai_client_id"', start)
            if end < 0:
                end = normalized.find("openai_client_id", start)
            if end < 0:
                end = min(len(normalized), start + 4000)
            else:
                end = min(len(normalized), end + 600)

            workspace_chunk = normalized[start:end]
            ids = re.findall(r'"id"(?:,|:)"([0-9a-fA-F-]{36})"', workspace_chunk)
            if not ids:
                return None

            kinds = re.findall(r'"kind"(?:,|:)"([^"]+)"', workspace_chunk)
            workspaces = []
            seen = set()
            for idx, wid in enumerate(ids):
                if wid in seen:
                    continue
                seen.add(wid)
                item = {"id": wid}
                if idx < len(kinds):
                    item["kind"] = kinds[idx]
                workspaces.append(item)

            if not workspaces:
                return None

            return {
                "session_id": session_id,
                "openai_client_id": client_id,
                "workspaces": workspaces,
            }

        candidates = [html]

        for quoted in re.findall(
            r'streamController\.enqueue\(("(?:\\.|[^"\\])*")\)',
            html,
            re.S,
        ):
            try:
                decoded = json.loads(quoted)
            except Exception:
                continue
            if decoded:
                candidates.append(decoded)

        if '\\"' in html:
            candidates.append(html.replace('\\"', '"'))

        for candidate in candidates:
            parsed = _build_from_text(candidate)
            if parsed and parsed.get("workspaces"):
                return parsed

        return None

    def _decode_oauth_session_cookie(self):
        """解码 oai-client-auth-session cookie"""
        try:
            for cookie in self.session.cookies:
                try:
                    name = cookie.name if hasattr(cookie, "name") else str(cookie)
                    if name == "oai-client-auth-session":
                        value = (
                            cookie.value
                            if hasattr(cookie, "value")
                            else self.session.cookies.get(name)
                        )
                        if value:
                            data = self._decode_cookie_json_value(value)
                            if data:
                                return data
                except Exception:
                    continue
        except Exception:
            pass

        return None

    @staticmethod
    def _decode_cookie_json_value(value):
        import base64
        import json

        raw_value = str(value or "").strip()
        if not raw_value:
            return None

        candidates = [raw_value]
        if "." in raw_value:
            candidates.insert(0, raw_value.split(".", 1)[0])

        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            padded = candidate + "=" * (-len(candidate) % 4)
            for decoder in (base64.urlsafe_b64decode, base64.b64decode):
                try:
                    decoded = decoder(padded).decode("utf-8")
                    parsed = json.loads(decoded)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    return parsed

        return None

    def _exchange_code_for_tokens(self, code, code_verifier, user_agent, impersonate):
        """用 authorization code 换取 tokens"""
        url = f"{self.oauth_issuer}/oauth/token"

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.oauth_redirect_uri,
            "client_id": self.oauth_client_id,
            "code_verifier": code_verifier,
        }

        headers = self._headers(
            url,
            user_agent=user_agent,
            accept="application/json",
            referer=f"{self.oauth_issuer}/sign-in-with-chatgpt/codex/consent",
            origin=self.oauth_issuer,
            content_type="application/x-www-form-urlencoded",
            fetch_site="same-origin",
        )

        try:
            kwargs = {"data": payload, "headers": headers, "timeout": 60}
            if impersonate:
                kwargs["impersonate"] = impersonate

            self._browser_pause()
            r = self.session.post(url, **kwargs)

            if r.status_code == 200:
                return r.json()
            else:
                self._set_error(f"换取 tokens 失败: {r.status_code} - {r.text[:200]}")

        except Exception as e:
            self._set_error(f"换取 tokens 异常: {e}")

        return None

    def _send_phone_number(self, phone, device_id, user_agent, sec_ch_ua, impersonate):
        request_url = f"{self.oauth_issuer}/api/accounts/add-phone/send"
        headers = self._headers(
            request_url,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            accept="application/json",
            referer=f"{self.oauth_issuer}/add-phone",
            origin=self.oauth_issuer,
            content_type="application/json",
            fetch_site="same-origin",
            extra_headers={"oai-device-id": device_id},
        )
        headers.update(generate_datadog_trace())

        try:
            kwargs = {
                "json": {"phone_number": phone},
                "headers": headers,
                "timeout": 30,
                "allow_redirects": False,
            }
            if impersonate:
                kwargs["impersonate"] = impersonate

            self._browser_pause(0.12, 0.25)
            resp = self.session.post(request_url, **kwargs)
        except Exception as e:
            return False, None, f"add-phone/send 异常: {e}"

        self._log(f"/add-phone/send -> {resp.status_code}")
        if resp.status_code != 200:
            return (
                False,
                None,
                f"add-phone/send 失败: {resp.status_code} - {resp.text[:180]}",
            )

        try:
            data = resp.json()
        except Exception:
            return False, None, "add-phone/send 响应不是 JSON"

        next_state = self._state_from_payload(
            data, current_url=str(resp.url) or request_url
        )
        self._log(f"add-phone/send {describe_flow_state(next_state)}")
        return True, next_state, ""

    def _resend_phone_otp(
        self, device_id, user_agent, sec_ch_ua, impersonate, state: FlowState
    ):
        request_url = f"{self.oauth_issuer}/api/accounts/phone-otp/resend"
        headers = self._headers(
            request_url,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            accept="application/json",
            referer=state.current_url
            or state.continue_url
            or f"{self.oauth_issuer}/phone-verification",
            origin=self.oauth_issuer,
            fetch_site="same-origin",
            extra_headers={"oai-device-id": device_id},
        )
        headers.update(generate_datadog_trace())

        try:
            kwargs = {"headers": headers, "timeout": 30, "allow_redirects": False}
            if impersonate:
                kwargs["impersonate"] = impersonate
            self._browser_pause(0.12, 0.25)
            resp = self.session.post(request_url, **kwargs)
        except Exception as e:
            return False, f"phone-otp/resend 异常: {e}"

        self._log(f"/phone-otp/resend -> {resp.status_code}")
        if resp.status_code == 200:
            return True, ""
        return False, f"phone-otp/resend 失败: {resp.status_code} - {resp.text[:180]}"

    def _validate_phone_otp(
        self, code, device_id, user_agent, sec_ch_ua, impersonate, state: FlowState
    ):
        request_url = f"{self.oauth_issuer}/api/accounts/phone-otp/validate"
        headers = self._headers(
            request_url,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            accept="application/json",
            referer=state.current_url
            or state.continue_url
            or f"{self.oauth_issuer}/phone-verification",
            origin=self.oauth_issuer,
            content_type="application/json",
            fetch_site="same-origin",
            extra_headers={"oai-device-id": device_id},
        )
        headers.update(generate_datadog_trace())

        try:
            kwargs = {
                "json": {"code": code},
                "headers": headers,
                "timeout": 30,
                "allow_redirects": False,
            }
            if impersonate:
                kwargs["impersonate"] = impersonate
            self._browser_pause(0.12, 0.25)
            resp = self.session.post(request_url, **kwargs)
        except Exception as e:
            return False, None, f"phone-otp/validate 异常: {e}"

        self._log(f"/phone-otp/validate -> {resp.status_code}")
        if resp.status_code != 200:
            if resp.status_code == 401:
                return False, None, "手机号验证码错误"
            return (
                False,
                None,
                f"phone-otp/validate 失败: {resp.status_code} - {resp.text[:180]}",
            )

        try:
            data = resp.json()
        except Exception:
            return False, None, "phone-otp/validate 响应不是 JSON"

        next_state = self._state_from_payload(
            data, current_url=str(resp.url) or request_url
        )
        self._log(f"手机号 OTP 验证通过 {describe_flow_state(next_state)}")
        return True, next_state, ""

    def _handle_add_phone_verification(
        self, device_id, user_agent, sec_ch_ua, impersonate, state: FlowState
    ):
        phone_service = SMSToMePhoneService(self.config, log_fn=self._log)
        if not phone_service.enabled:
            self._set_error(
                "OAuth 登录被 add_phone 阻断，当前账号需要手机号验证；未配置可用的 SMSToMe 号码池"
            )
            return None

        excluded_prefixes = set()
        last_failure = ""

        for attempt in range(phone_service.max_attempts):
            try:
                entry = phone_service.acquire_phone(exclude_prefixes=excluded_prefixes)
            except Exception as e:
                last_failure = f"获取手机号失败: {e}"
                self._log(last_failure)
                break

            if not entry:
                last_failure = last_failure or "SMSToMe 号码池中无可用手机号"
                break

            prefix = phone_service.prefix_hint(entry.phone)
            self._log(
                f"步骤5: add_phone 选择手机号 {attempt + 1}/{phone_service.max_attempts}: {entry.phone} ({entry.country_slug})"
            )

            sent, next_state, detail = self._send_phone_number(
                entry.phone,
                device_id,
                user_agent,
                sec_ch_ua,
                impersonate,
            )
            if not sent or not next_state:
                last_failure = detail or "add-phone/send 未返回有效状态"
                self._log(last_failure)
                self._blacklist_phone_if_needed(phone_service, entry, last_failure)
                excluded_prefixes.add(prefix)
                continue

            if (
                next_state.page_type != "phone_otp_verification"
                and "phone-verification"
                not in f"{next_state.continue_url} {next_state.current_url}".lower()
            ):
                last_failure = f"add-phone/send 未进入手机验证码页: {describe_flow_state(next_state)}"
                self._log(last_failure)
                self._blacklist_phone_if_needed(
                    phone_service, entry, last_failure, next_state
                )
                excluded_prefixes.add(prefix)
                continue

            session_data = self._decode_oauth_session_cookie() or {}
            verification_channel = (
                str(session_data.get("phone_verification_channel") or "sms")
                .strip()
                .lower()
                or "sms"
            )
            bound_phone = (
                str(session_data.get("phone_number") or entry.phone).strip()
                or entry.phone
            )
            self._log(
                f"add_phone 发码成功: phone={bound_phone}, channel={verification_channel}"
            )

            if verification_channel != "sms":
                last_failure = f"add_phone 已切到 {verification_channel} 通道，当前 SMSToMe 仅支持短信接码"
                self._log(last_failure)
                excluded_prefixes.add(prefix)
                continue

            code = phone_service.wait_for_code(entry)
            if not code:
                self._log("手机号验证码暂未收到，尝试重发一次...")
                resend_ok, resend_detail = self._resend_phone_otp(
                    device_id,
                    user_agent,
                    sec_ch_ua,
                    impersonate,
                    next_state,
                )
                if resend_ok:
                    code = phone_service.wait_for_code(entry)
                if not code:
                    last_failure = (
                        resend_detail or f"手机号 {entry.phone} 未收到短信验证码"
                    )
                    self._log(last_failure)
                    excluded_prefixes.add(prefix)
                    continue

            valid, validated_state, detail = self._validate_phone_otp(
                code,
                device_id,
                user_agent,
                sec_ch_ua,
                impersonate,
                next_state,
            )
            if not valid or not validated_state:
                last_failure = detail or "手机号 OTP 验证失败"
                self._log(last_failure)
                excluded_prefixes.add(prefix)
                continue

            return validated_state

        self._set_error(f"add_phone 阶段失败: {last_failure or '未完成手机号验证'}")
        return None

    def _handle_otp_verification(
        self,
        email,
        device_id,
        user_agent,
        sec_ch_ua,
        impersonate,
        skymail_client,
        state,
    ):
        """处理 OAuth 阶段的邮箱 OTP 验证，返回服务端声明的下一步状态。"""
        self._log("步骤4: 检测到邮箱 OTP 验证")

        request_url = f"{self.oauth_issuer}/api/accounts/email-otp/validate"
        headers_otp = self._headers(
            request_url,
            user_agent=user_agent,
            sec_ch_ua=sec_ch_ua,
            accept="application/json",
            referer=state.current_url
            or state.continue_url
            or f"{self.oauth_issuer}/email-verification",
            origin=self.oauth_issuer,
            content_type="application/json",
            fetch_site="same-origin",
            extra_headers={
                "oai-device-id": device_id,
            },
        )
        headers_otp.update(generate_datadog_trace())

        if not hasattr(skymail_client, "_used_codes"):
            skymail_client._used_codes = set()

        tried_codes = set(getattr(skymail_client, "_used_codes", set()))
        otp_deadline = time.time() + 60
        otp_sent_at = time.time()

        def validate_otp(code):
            tried_codes.add(code)
            self._log(f"尝试 OTP: {code}")

            try:
                kwargs = {
                    "json": {"code": code},
                    "headers": headers_otp,
                    "timeout": 30,
                    "allow_redirects": False,
                }
                if impersonate:
                    kwargs["impersonate"] = impersonate

                self._browser_pause(0.12, 0.25)
                resp_otp = self.session.post(request_url, **kwargs)
            except Exception as e:
                self._log(f"email-otp/validate 异常: {e}")
                return None

            self._log(f"/email-otp/validate -> {resp_otp.status_code}")
            if resp_otp.status_code != 200:
                self._log(f"OTP 无效: {resp_otp.text[:160]}")
                return None

            try:
                otp_data = resp_otp.json()
            except Exception:
                self._log("email-otp/validate 响应不是 JSON")
                return None

            next_state = self._state_from_payload(
                otp_data,
                current_url=str(resp_otp.url)
                or (state.current_url or state.continue_url or request_url),
            )
            self._log(f"OTP 验证通过 {describe_flow_state(next_state)}")
            skymail_client._used_codes.add(code)
            return next_state

        if hasattr(skymail_client, "wait_for_verification_code"):
            self._log("使用 wait_for_verification_code 进行阻塞式获取新验证码...")
            while time.time() < otp_deadline:
                remaining = max(1, int(otp_deadline - time.time()))
                wait_time = min(10, remaining)
                try:
                    code = skymail_client.wait_for_verification_code(
                        email,
                        timeout=wait_time,
                        otp_sent_at=otp_sent_at,
                        exclude_codes=tried_codes,
                    )
                except Exception as e:
                    self._log(f"等待 OTP 异常: {e}")
                    code = None

                if not code:
                    self._log("暂未收到新的 OTP，继续等待...")
                    if self.last_error:
                        break
                    continue

                if code in tried_codes:
                    self._log(f"跳过已尝试验证码: {code}")
                    continue

                next_state = validate_otp(code)
                if next_state:
                    return next_state
                if self.last_error:
                    break
        else:
            while time.time() < otp_deadline:
                messages = skymail_client.fetch_emails(email) or []
                candidate_codes = []

                for msg in messages[:12]:
                    content = msg.get("content") or msg.get("text") or ""
                    code = skymail_client.extract_verification_code(content)
                    if code and code not in tried_codes:
                        candidate_codes.append(code)

                if not candidate_codes:
                    elapsed = int(60 - max(0, otp_deadline - time.time()))
                    self._log(f"等待新的 OTP... ({elapsed}s/60s)")
                    time.sleep(2)
                    continue

                for otp_code in candidate_codes:
                    next_state = validate_otp(otp_code)
                    if next_state:
                        return next_state

                time.sleep(2)
                if self.last_error:
                    break

        if not self.last_error:
            self._set_error(
                f"OAuth 阶段 OTP 验证失败，已尝试 {len(tried_codes)} 个验证码"
            )
        return None
