"""
Token 刷新模块
支持 Session Token 和 OAuth Refresh Token 两种刷新方式
"""

from __future__ import annotations

import logging
import json
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from curl_cffi import requests as cffi_requests

# from ..config.settings import get_settings  # removed: external dep
# from ..database.session import get_db  # removed: external dep
# from ..database import crud  # removed: external dep
# from ..database.models import Account  # removed: external dep

logger = logging.getLogger(__name__)


@dataclass
class TokenRefreshResult:
    """Token 刷新结果"""
    success: bool
    access_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[datetime] = None
    error_message: str = ""


class TokenRefreshManager:
    """
    Token 刷新管理器
    支持两种刷新方式：
    1. Session Token 刷新（优先）
    2. OAuth Refresh Token 刷新
    """

    # OpenAI OAuth 端点
    SESSION_URL = "https://chatgpt.com/api/auth/session"
    TOKEN_URL = "https://auth.openai.com/oauth/token"

    def __init__(self, proxy_url: Optional[str] = None):
        """
        初始化 Token 刷新管理器

        Args:
            proxy_url: 代理 URL
        """
        self.proxy_url = proxy_url
        from .constants import OAUTH_CLIENT_ID, OAUTH_REDIRECT_URI
        self._oauth_client_id = OAUTH_CLIENT_ID
        self._oauth_redirect_uri = OAUTH_REDIRECT_URI

    def _create_session(self) -> cffi_requests.Session:
        """创建 HTTP 会话"""
        session = cffi_requests.Session(impersonate="chrome120", proxy=self.proxy_url)
        return session

    def refresh_by_session_token(self, session_token: str) -> TokenRefreshResult:
        """
        使用 Session Token 刷新

        Args:
            session_token: 会话令牌

        Returns:
            TokenRefreshResult: 刷新结果
        """
        result = TokenRefreshResult(success=False)

        try:
            session = self._create_session()

            # 设置会话 Cookie
            session.cookies.set(
                "__Secure-next-auth.session-token",
                session_token,
                domain=".chatgpt.com",
                path="/"
            )

            # 请求会话端点
            response = session.get(
                self.SESSION_URL,
                headers={
                    "accept": "application/json",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=30
            )

            if response.status_code != 200:
                result.error_message = f"Session token 刷新失败: HTTP {response.status_code}"
                logger.warning(result.error_message)
                return result

            data = response.json()

            # 提取 access_token
            access_token = data.get("accessToken")
            if not access_token:
                result.error_message = "Session token 刷新失败: 未找到 accessToken"
                logger.warning(result.error_message)
                return result

            # 提取过期时间
            expires_at = None
            expires_str = data.get("expires")
            if expires_str:
                try:
                    expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse expiration date '{expires_str}': {e}")

            result.success = True
            result.access_token = access_token
            result.expires_at = expires_at

            logger.info(f"Session token 刷新成功，过期时间: {expires_at}")
            return result

        except Exception as e:
            result.error_message = f"Session token 刷新异常: {str(e)}"
            logger.error(result.error_message)
            return result

    def refresh_by_oauth_token(
        self,
        refresh_token: str,
        client_id: Optional[str] = None
    ) -> TokenRefreshResult:
        """
        使用 OAuth Refresh Token 刷新

        Args:
            refresh_token: OAuth 刷新令牌
            client_id: OAuth Client ID

        Returns:
            TokenRefreshResult: 刷新结果
        """
        result = TokenRefreshResult(success=False)

        try:
            session = self._create_session()

            # 使用配置的 client_id 或默认值
            client_id = client_id or self._oauth_client_id

            # 构建请求体
            token_data = {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "redirect_uri": self._oauth_redirect_uri
            }

            response = session.post(
                self.TOKEN_URL,
                headers={
                    "content-type": "application/x-www-form-urlencoded",
                    "accept": "application/json"
                },
                data=token_data,
                timeout=30
            )

            if response.status_code != 200:
                result.error_message = f"OAuth token 刷新失败: HTTP {response.status_code}"
                logger.warning(f"{result.error_message}, 响应: {response.text[:200]}")
                return result

            data = response.json()

            # 提取令牌
            access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in", 3600)

            if not access_token:
                result.error_message = "OAuth token 刷新失败: 未找到 access_token"
                logger.warning(result.error_message)
                return result

            # 计算过期时间
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            result.success = True
            result.access_token = access_token
            result.refresh_token = new_refresh_token
            result.expires_at = expires_at

            logger.info(f"OAuth token 刷新成功，过期时间: {expires_at}")
            return result

        except Exception as e:
            result.error_message = f"OAuth token 刷新异常: {str(e)}"
            logger.error(result.error_message)
            return result

    def refresh_account(self, account: Account) -> TokenRefreshResult:
        """
        刷新账号的 Token

        优先级：
        1. Session Token 刷新
        2. OAuth Refresh Token 刷新

        Args:
            account: 账号对象

        Returns:
            TokenRefreshResult: 刷新结果
        """
        # 优先尝试 Session Token
        if account.session_token:
            logger.info(f"尝试使用 Session Token 刷新账号 {account.email}")
            result = self.refresh_by_session_token(account.session_token)
            if result.success:
                return result
            logger.warning(f"Session Token 刷新失败，尝试 OAuth 刷新")

        # 尝试 OAuth Refresh Token
        if account.refresh_token:
            logger.info(f"尝试使用 OAuth Refresh Token 刷新账号 {account.email}")
            result = self.refresh_by_oauth_token(
                refresh_token=account.refresh_token,
                client_id=account.client_id
            )
            return result

        # 无可用刷新方式
        return TokenRefreshResult(
            success=False,
            error_message="账号没有可用的刷新方式（缺少 session_token 和 refresh_token）"
        )

    def validate_token(self, access_token: str) -> Tuple[bool, Optional[str]]:
        """
        验证 Access Token 是否有效

        Args:
            access_token: 访问令牌

        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        try:
            session = self._create_session()

            # 调用 OpenAI API 验证 token
            response = session.get(
                "https://chatgpt.com/backend-api/me",
                headers={
                    "authorization": f"Bearer {access_token}",
                    "accept": "application/json"
                },
                timeout=30
            )

            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Token 无效或已过期"
            elif response.status_code == 403:
                return False, "账号可能被封禁"
            else:
                return False, f"验证失败: HTTP {response.status_code}"

        except Exception as e:
            return False, f"验证异常: {str(e)}"


def refresh_account_token(account_id: int, proxy_url: Optional[str] = None) -> TokenRefreshResult:
    """
    刷新指定账号的 Token 并更新数据库

    Args:
        account_id: 账号 ID
        proxy_url: 代理 URL

    Returns:
        TokenRefreshResult: 刷新结果
    """
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            return TokenRefreshResult(success=False, error_message="账号不存在")

        manager = TokenRefreshManager(proxy_url=proxy_url)
        result = manager.refresh_account(account)

        if result.success:
            # 更新数据库
            update_data = {
                "access_token": result.access_token,
                "last_refresh": datetime.utcnow()
            }

            if result.refresh_token:
                update_data["refresh_token"] = result.refresh_token

            if result.expires_at:
                update_data["expires_at"] = result.expires_at

            crud.update_account(db, account_id, **update_data)

        return result


def validate_account_token(account_id: int, proxy_url: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    验证指定账号的 Token 是否有效

    Args:
        account_id: 账号 ID
        proxy_url: 代理 URL

    Returns:
        Tuple[bool, Optional[str]]: (是否有效, 错误信息)
    """
    with get_db() as db:
        account = crud.get_account_by_id(db, account_id)
        if not account:
            return False, "账号不存在"

        if not account.access_token:
            return False, "账号没有 access_token"

        manager = TokenRefreshManager(proxy_url=proxy_url)
        return manager.validate_token(account.access_token)
