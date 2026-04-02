"""
注册流程引擎 V2
基于 curl_cffi 的注册状态机，注册成功后直接复用同一会话提取 ChatGPT Session。
"""

import time
import logging
from datetime import datetime
from typing import Optional, Callable

from core.base_platform import AccountStatus
from platforms.chatgpt.register import RegistrationResult

from .chatgpt_client import ChatGPTClient
from .oauth_client import OAuthClient
from .utils import generate_random_name, generate_random_birthday

logger = logging.getLogger(__name__)

class EmailServiceAdapter:
    """\u5c06 V1 \u7684 email_service \u9002\u914d\u6210 V2 \u6240\u9700\u7684\u63a5\u7801\u63a5\u53e3\u3002"""
    def __init__(self, email_service, email, log_fn):
        self.es = email_service
        self.email = email
        self.log_fn = log_fn
        self._used_codes = set()

    def wait_for_verification_code(self, email, timeout=60, otp_sent_at=None, exclude_codes=None):
        """\u5728\u6307\u5b9a\u65f6\u95f4\u7a97\u53e3\u5185\u7b49\u5f85\u672a\u4f7f\u7528\u7684\u65b0\u9a8c\u8bc1\u7801\uff0c\u81ea\u52a8\u5ffd\u7565\u90ae\u7bb1\u670d\u52a1\u91cd\u590d\u8fd4\u56de\u7684\u65e7\u7801\u3002AI by zb"""
        total_timeout = max(1, int(timeout or 0))
        blocked_codes = set(exclude_codes or []) | set(self._used_codes)
        deadline = time.time() + total_timeout
        duplicate_code = None
        duplicate_hits = 0

        self.log_fn(f"\u6b63\u5728\u7b49\u5f85\u90ae\u7bb1 {email} \u7684\u9a8c\u8bc1\u7801 ({total_timeout}s)...")

        while time.time() < deadline:
            remaining = max(1, int(deadline - time.time()))
            try:
                code = self.es.get_verification_code(
                    timeout=remaining,
                    otp_sent_at=otp_sent_at,
                    exclude_codes=blocked_codes,
                )
            except TimeoutError:
                break

            if not code:
                break

            code = str(code).strip()
            if not code:
                break

            if code in blocked_codes:
                duplicate_hits = duplicate_hits + 1 if code == duplicate_code else 1
                duplicate_code = code
                if duplicate_hits == 1 or duplicate_hits % 3 == 0:
                    suffix = f"\uff08\u91cd\u590d {duplicate_hits} \u6b21\uff09" if duplicate_hits > 1 else ""
                    self.log_fn(f"\u90ae\u7bb1\u8fd4\u56de\u4e86\u5df2\u5904\u7406\u7684\u65e7\u9a8c\u8bc1\u7801\uff0c\u7ee7\u7eed\u7b49\u5f85\u65b0\u9a8c\u8bc1\u7801: {code}{suffix}")
                cooldown = min(1.5, max(0.0, deadline - time.time()))
                if cooldown > 0:
                    time.sleep(cooldown)
                continue

            self._used_codes.add(code)
            self.log_fn(f"\u6210\u529f\u83b7\u53d6\u9a8c\u8bc1\u7801: {code}")
            return code

        if duplicate_code and duplicate_hits:
            self.log_fn(f"\u7b49\u5f85\u65b0\u9a8c\u8bc1\u7801\u8d85\u65f6\uff0c\u671f\u95f4\u4ec5\u6536\u5230\u91cd\u590d\u9a8c\u8bc1\u7801: {duplicate_code}\uff08\u5171 {duplicate_hits} \u6b21\uff09")
        return None

class RegistrationEngineV2:
    def __init__(
        self,
        email_service,
        proxy_url: Optional[str] = None,
        browser_mode: str = "protocol",
        callback_logger: Optional[Callable[[str], None]] = None,
        task_uuid: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.email_service = email_service
        self.proxy_url = proxy_url
        self.browser_mode = browser_mode or "protocol"
        self.callback_logger = callback_logger
        self.task_uuid = task_uuid
        self.max_retries = max(1, int(max_retries or 1))
        
        self.email = None
        self.password = None
        self.logs = []
        
    def _log(self, message: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.logs.append(log_message)
        if self.callback_logger:
            self.callback_logger(log_message)
        if level == "error":
            logger.error(log_message)
        else:
            logger.info(log_message)

    def _should_retry(self, message: str) -> bool:
        text = str(message or "").lower()
        retriable_markers = [
            "tls",
            "ssl",
            "curl: (35)",
            "预授权被拦截",
            "authorize",
            "registration_disallowed",
            "http 400",
            "创建账号失败",
            "未获取到 authorization code",
            "consent",
            "workspace",
            "organization",
            "otp",
            "验证码",
            "session",
            "accessToken",
            "next-auth",
        ]
        return any(marker.lower() in text for marker in retriable_markers)

    def _should_fetch_oauth_tokens(self) -> bool:
        """仅在已配置 ChatGPT 外部上传目标时才补拉 OAuth tokens。AI by zb"""
        try:
            from core.config_store import config_store
        except Exception as exc:
            self._log(f"读取上传配置失败，默认跳过 OAuth token 补拉: {exc}")
            return False

        upload_targets = {
            "CPA": str(config_store.get("cpa_api_url", "") or "").strip(),
            "Team Manager": str(config_store.get("team_manager_url", "") or "").strip(),
        }
        enabled_targets = [name for name, value in upload_targets.items() if value]
        if not enabled_targets:
            self._log("未配置 ChatGPT 外部上传目标，跳过 OAuth token 补拉")
            return False

        self._log(f"检测到已配置上传目标: {', '.join(enabled_targets)}")
        return True

    def _fetch_oauth_tokens(
        self,
        chatgpt_client: ChatGPTClient,
        email: str,
        password: str,
        skymail_adapter: EmailServiceAdapter,
    ) -> dict[str, str]:
        """复用当前注册会话补拉 OAuth tokens，尽量拿到 refresh_token。AI by zb"""

        oauth_client = OAuthClient(
            config={},
            proxy=self.proxy_url,
            verbose=False,
            browser_mode=self.browser_mode,
        )
        oauth_client.session = chatgpt_client.session
        oauth_client._log = self._log

        try:
            tokens = oauth_client.login_and_get_tokens(
                email,
                password,
                chatgpt_client.device_id,
                user_agent=chatgpt_client.ua,
                sec_ch_ua=chatgpt_client.sec_ch_ua,
                impersonate=chatgpt_client.impersonate,
                skymail_client=skymail_adapter,
            )
        except Exception as exc:
            self._log(f"OAuth token 补拉异常: {exc}")
            return {}

        if not isinstance(tokens, dict):
            self._log("OAuth token 补拉失败，继续仅保存 session/access token")
            return {}

        normalized_tokens = {
            "access_token": str(tokens.get("access_token") or "").strip(),
            "refresh_token": str(tokens.get("refresh_token") or "").strip(),
            "id_token": str(tokens.get("id_token") or "").strip(),
        }
        if not normalized_tokens["access_token"]:
            self._log("OAuth token 补拉未返回 access_token，继续仅保存 session/access token")
            return {}
        return normalized_tokens

    def run(self) -> RegistrationResult:
        result = RegistrationResult(success=False, logs=self.logs)
        try:
            last_error = ""
            for attempt in range(self.max_retries):
                try:
                    if attempt == 0:
                        self._log("=" * 60)
                        self._log("开始注册流程 V2 (Session 复用直取 AccessToken)")
                        self._log(f"请求模式: {self.browser_mode}")
                        self._log("=" * 60)
                    else:
                        self._log(f"整流程重试 {attempt + 1}/{self.max_retries} ...")
                        time.sleep(1)

                    # 1. 创建邮箱
                    email_data = self.email_service.create_email()
                    email_addr = self.email or (email_data.get('email') if email_data else None)
                    if not email_addr:
                        result.error_message = "创建邮箱失败"
                        return result

                    result.email = email_addr

                    pwd = self.password or "AAb1234567890!"
                    result.password = pwd

                    # 随机姓名、生日
                    first_name, last_name = generate_random_name()
                    birthdate = generate_random_birthday()

                    self._log(f"邮箱: {email_addr}, 密码: {pwd}")
                    self._log(f"注册信息: {first_name} {last_name}, 生日: {birthdate}")

                    # 使用包装器为底层客户端提供接码服务
                    skymail_adapter = EmailServiceAdapter(self.email_service, email_addr, self._log)

                    # 2. 初始化 V2 客户端
                    chatgpt_client = ChatGPTClient(
                        proxy=self.proxy_url,
                        verbose=False,
                        browser_mode=self.browser_mode,
                    )
                    chatgpt_client._log = self._log

                    self._log("步骤 1/2: 执行注册状态机...")

                    success, msg = chatgpt_client.register_complete_flow(
                        email_addr, pwd, first_name, last_name, birthdate, skymail_adapter
                    )

                    if not success:
                        last_error = f"注册流失败: {msg}"
                        if attempt < self.max_retries - 1 and self._should_retry(msg):
                            self._log(f"注册流失败，准备整流程重试: {msg}")
                            continue
                        result.error_message = last_error
                        return result

                    self._log("步骤 2/2: 复用注册会话，直接获取 ChatGPT Session / AccessToken...")
                    session_ok, session_result = chatgpt_client.reuse_session_and_get_tokens()

                    if session_ok:
                        self._log("Token 提取完成！")
                        result.success = True
                        result.access_token = session_result.get("access_token", "")
                        result.session_token = session_result.get("session_token", "")
                        result.account_id = (
                            session_result.get("account_id")
                            or session_result.get("user_id")
                            or ("v2_acct_" + chatgpt_client.device_id[:8])
                        )
                        result.workspace_id = session_result.get("workspace_id", "")
                        result.metadata = {
                            "auth_provider": session_result.get("auth_provider", ""),
                            "expires": session_result.get("expires", ""),
                            "user_id": session_result.get("user_id", ""),
                            "user": session_result.get("user") or {},
                            "account": session_result.get("account") or {},
                            "oauth_refresh_token_available": False,
                        }

                        if self._should_fetch_oauth_tokens():
                            self._log("附加步骤: 检测到上传目标配置，尝试复用当前登录态换取 OAuth Tokens...")
                            oauth_tokens = self._fetch_oauth_tokens(
                                chatgpt_client,
                                email_addr,
                                pwd,
                                skymail_adapter,
                            )
                            if oauth_tokens:
                                result.access_token = oauth_tokens.get("access_token", "") or result.access_token
                                result.refresh_token = oauth_tokens.get("refresh_token", "")
                                result.id_token = oauth_tokens.get("id_token", "")
                                result.metadata["oauth_refresh_token_available"] = bool(result.refresh_token)
                                if result.refresh_token:
                                    self._log("OAuth refresh_token 补拉成功")
                                else:
                                    self._log("OAuth token 补拉完成，但未返回 refresh_token")
                            result.metadata["oauth_token_fetch_skipped"] = False
                        else:
                            result.metadata["oauth_token_fetch_skipped"] = True

                        if result.workspace_id:
                            self._log(f"Session Workspace ID: {result.workspace_id}")

                        self._log("=" * 60)
                        self._log("注册流程成功结束!")
                        self._log("=" * 60)
                        return result

                    last_error = f"注册成功，但复用会话获取 AccessToken 失败: {session_result}"
                    if attempt < self.max_retries - 1:
                        self._log(f"{last_error}，准备整流程重试")
                        continue
                    result.error_message = last_error
                    return result
                except Exception as attempt_error:
                    last_error = str(attempt_error)
                    if attempt < self.max_retries - 1 and self._should_retry(last_error):
                        self._log(f"本轮出现异常，准备整流程重试: {last_error}")
                        continue
                    raise

            result.error_message = last_error or "注册失败"
            return result
                
        except Exception as e:
            self._log(f"V2 注册全流程执行异常: {e}", "error")
            import traceback
            traceback.print_exc()
            result.error_message = str(e)
            return result
