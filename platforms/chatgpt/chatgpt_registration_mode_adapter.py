"""ChatGPT 注册模式适配器。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from core.base_platform import Account, AccountStatus

CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN = "refresh_token"
CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY = "access_token_only"
DEFAULT_CHATGPT_REGISTRATION_MODE = CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN


def normalize_chatgpt_registration_mode(value) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {
        CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
        "access_token",
        "at_only",
        "without_rt",
        "without_refresh_token",
        "no_rt",
        "0",
        "false",
    }:
        return CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY
    if normalized in {
        CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
        "rt",
        "with_rt",
        "has_rt",
        "1",
        "true",
    }:
        return CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN
    return DEFAULT_CHATGPT_REGISTRATION_MODE


def resolve_chatgpt_registration_mode(extra: Optional[dict]) -> str:
    extra = extra or {}
    if "chatgpt_registration_mode" in extra:
        return normalize_chatgpt_registration_mode(extra.get("chatgpt_registration_mode"))
    if "chatgpt_has_refresh_token_solution" in extra:
        return (
            CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN
            if bool(extra.get("chatgpt_has_refresh_token_solution"))
            else CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY
        )
    return DEFAULT_CHATGPT_REGISTRATION_MODE


@dataclass(frozen=True)
class ChatGPTRegistrationContext:
    email_service: object
    proxy_url: Optional[str]
    callback_logger: Callable[[str], None]
    email: Optional[str]
    password: Optional[str]
    browser_mode: str
    max_retries: int
    extra_config: dict


class BaseChatGPTRegistrationModeAdapter(ABC):
    mode: str

    @abstractmethod
    def _create_engine(self, context: ChatGPTRegistrationContext):
        """按模式构造底层注册引擎。"""

    def run(self, context: ChatGPTRegistrationContext):
        _MAILBOX_ERROR_MARKERS = ("service_abuse_mode", "oauth_token_failed")
        _MAX_ATTEMPTS = 3
        result = None
        for _attempt in range(_MAX_ATTEMPTS):
            engine = self._create_engine(context)
            if context.email is not None:
                engine.email = context.email
            if context.password is not None:
                engine.password = context.password
            result = engine.run()
            if result.success:
                return result
            err = str(getattr(result, "error_message", "") or "")
            matched_marker = next((m for m in _MAILBOX_ERROR_MARKERS if m in err), None)
            if matched_marker and _attempt < _MAX_ATTEMPTS - 1:
                context.callback_logger(
                    f"邮箱 OAuth token 已失效（{matched_marker}），"
                    f"换用下一个邮箱重试 ({_attempt + 1}/{_MAX_ATTEMPTS - 1})..."
                )
                continue
            break
        return result

    def build_account(self, result, fallback_password: str) -> Account:
        return Account(
            platform="chatgpt",
            email=getattr(result, "email", ""),
            password=getattr(result, "password", "") or fallback_password,
            user_id=getattr(result, "account_id", ""),
            token=getattr(result, "access_token", ""),
            status=AccountStatus.REGISTERED,
            extra=self._build_account_extra(result),
        )

    def _build_account_extra(self, result) -> dict:
        return {
            "access_token": getattr(result, "access_token", ""),
            "refresh_token": getattr(result, "refresh_token", ""),
            "id_token": getattr(result, "id_token", ""),
            "session_token": getattr(result, "session_token", ""),
            "workspace_id": getattr(result, "workspace_id", ""),
            "chatgpt_registration_mode": self.mode,
            "chatgpt_has_refresh_token_solution": self.mode == CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
            "chatgpt_token_source": getattr(result, "source", "register"),
        }


class RefreshTokenChatGPTRegistrationAdapter(BaseChatGPTRegistrationModeAdapter):
    mode = CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN

    def _create_engine(self, context: ChatGPTRegistrationContext):
        from platforms.chatgpt.refresh_token_registration_engine import RefreshTokenRegistrationEngine

        return RefreshTokenRegistrationEngine(
            email_service=context.email_service,
            proxy_url=context.proxy_url,
            callback_logger=context.callback_logger,
            browser_mode=context.browser_mode,
            max_retries=context.max_retries,
            extra_config=context.extra_config,
        )


class AccessTokenOnlyChatGPTRegistrationAdapter(BaseChatGPTRegistrationModeAdapter):
    mode = CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY

    def _create_engine(self, context: ChatGPTRegistrationContext):
        from platforms.chatgpt.access_token_only_registration_engine import AccessTokenOnlyRegistrationEngine

        return AccessTokenOnlyRegistrationEngine(
            email_service=context.email_service,
            proxy_url=context.proxy_url,
            browser_mode=context.browser_mode,
            callback_logger=context.callback_logger,
            max_retries=context.max_retries,
            extra_config=context.extra_config,
        )


def build_chatgpt_registration_mode_adapter(
    extra: Optional[dict],
) -> BaseChatGPTRegistrationModeAdapter:
    mode = resolve_chatgpt_registration_mode(extra)
    if mode == CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY:
        return AccessTokenOnlyChatGPTRegistrationAdapter()
    return RefreshTokenChatGPTRegistrationAdapter()
