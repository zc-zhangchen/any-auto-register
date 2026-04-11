"""
注册流程引擎 V2
基于 curl_cffi 的注册状态机，注册成功后直接复用同一会话提取 ChatGPT Session。
"""

import time
import logging
from datetime import datetime
from typing import Optional, Callable

from core.task_runtime import TaskInterruption
from platforms.chatgpt.refresh_token_registration_engine import RegistrationResult

from .chatgpt_client import ChatGPTClient
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
        msg = f"\u6b63\u5728\u7b49\u5f85\u90ae\u7bb1 {email} \u7684\u9a8c\u8bc1\u7801 ({timeout}s)..."
        self.log_fn(msg)
        code = self.es.get_verification_code(
            timeout=timeout,
            otp_sent_at=otp_sent_at,
            exclude_codes=exclude_codes if exclude_codes is not None else self._used_codes,
        )
        if code:
            self._used_codes.add(code)
            self.log_fn(f"\u6210\u529f\u83b7\u53d6\u9a8c\u8bc1\u7801: {code}")
        return code

class AccessTokenOnlyRegistrationEngine:
    def __init__(
        self,
        email_service,
        proxy_url: Optional[str] = None,
        browser_mode: str = "protocol",
        callback_logger: Optional[Callable[[str], None]] = None,
        task_uuid: Optional[str] = None,
        max_retries: int = 3,
        extra_config: Optional[dict] = None,
    ):
        self.email_service = email_service
        self.proxy_url = proxy_url
        self.browser_mode = browser_mode or "protocol"
        self.callback_logger = callback_logger
        self.task_uuid = task_uuid
        self.max_retries = max(1, int(max_retries or 1))
        self.extra_config = dict(extra_config or {})
        
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
                        }

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
                except TaskInterruption:
                    raise
                except Exception as attempt_error:
                    last_error = str(attempt_error)
                    if attempt < self.max_retries - 1 and self._should_retry(last_error):
                        self._log(f"本轮出现异常，准备整流程重试: {last_error}")
                        continue
                    raise

            result.error_message = last_error or "注册失败"
            return result
                
        except TaskInterruption:
            raise
        except Exception as e:
            self._log(f"无 RT 注册全流程执行异常: {e}", "error")
            import traceback
            traceback.print_exc()
            result.error_message = str(e)
            return result


# 兼容旧命名，逐步迁移到更见名知意的类名。
RegistrationEngineV2 = AccessTokenOnlyRegistrationEngine
