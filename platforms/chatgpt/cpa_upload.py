"""
CPA (Codex Protocol API) 上传功能
"""

import json
import base64
import logging
from typing import Tuple
from datetime import datetime, timezone, timedelta
import hashlib
from pathlib import Path

from curl_cffi import requests as cffi_requests
from curl_cffi import CurlMime

logger = logging.getLogger(__name__)


def _decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def _b64url_json(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _derive_display_name(email: str) -> str:
    local = (email or "").split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ")
    parts = [part for part in local.split() if part]
    if not parts:
        return "OpenAI User"
    return " ".join(part[:1].upper() + part[1:] for part in parts[:3])


def _get_auth_info(payload: dict) -> dict:
    nested = payload.get("https://api.openai.com/auth", {})
    if isinstance(nested, dict) and nested:
        return nested

    flat = {}
    for key, value in payload.items():
        if key.startswith("https://api.openai.com/auth."):
            flat[key.split(".", 4)[-1]] = value
    return flat


def _build_compat_id_token(
    *,
    access_token: str,
    email: str,
) -> str:
    """
    基于 access_token 构造一个仅供本地 CPA/玩具环境解析的兼容 id_token。
    注意：该 token 仅用于不校验签名、只解析 payload 的本地兼容场景。
    """
    payload = _decode_jwt_payload(access_token)
    if not payload:
        return ""

    auth_info = _get_auth_info(payload)
    email_from_token = ((payload.get("https://api.openai.com/profile") or {}).get("email") or payload.get("email") or email or "").strip()
    email_verified = bool(
        ((payload.get("https://api.openai.com/profile") or {}).get("email_verified"))
        if isinstance(payload.get("https://api.openai.com/profile"), dict)
        else payload.get("email_verified", True)
    )
    account_id = str(auth_info.get("chatgpt_account_id") or auth_info.get("account_id") or "").strip()
    user_id = str(
        auth_info.get("chatgpt_user_id")
        or auth_info.get("user_id")
        or payload.get("sub")
        or ""
    ).strip()
    iat = int(payload.get("iat") or 0)
    exp = int(payload.get("exp") or 0)
    auth_time = int(payload.get("pwd_auth_time") or payload.get("auth_time") or iat or 0)
    session_id = str(payload.get("session_id") or f"compat_session_{(account_id or user_id or 'unknown').replace('-', '')[:24]}").strip()
    plan_type = str(auth_info.get("chatgpt_plan_type") or "free").strip() or "free"
    organization_id = str(auth_info.get("organization_id") or f"org-{hashlib.sha1((account_id or email_from_token or user_id).encode('utf-8')).hexdigest()[:24]}")
    project_id = str(auth_info.get("project_id") or f"proj_{hashlib.sha1((organization_id + ':' + (account_id or user_id)).encode('utf-8')).hexdigest()[:24]}")

    compat_auth = {
        "chatgpt_account_id": account_id,
        "chatgpt_plan_type": plan_type,
        "chatgpt_subscription_active_start": auth_info.get("chatgpt_subscription_active_start"),
        "chatgpt_subscription_active_until": auth_info.get("chatgpt_subscription_active_until"),
        "chatgpt_subscription_last_checked": auth_info.get("chatgpt_subscription_last_checked"),
        "chatgpt_user_id": user_id,
        "completed_platform_onboarding": bool(auth_info.get("completed_platform_onboarding", False)),
        "groups": auth_info.get("groups", []),
        "is_org_owner": bool(auth_info.get("is_org_owner", True)),
        "localhost": bool(auth_info.get("localhost", True)),
        "organization_id": organization_id,
        "organizations": auth_info.get("organizations") or [
            {
                "id": organization_id,
                "is_default": True,
                "role": "owner",
                "title": "Personal",
            }
        ],
        "project_id": project_id,
        "user_id": str(auth_info.get("user_id") or user_id or "").strip(),
    }

    compat_payload = {
        "amr": ["pwd", "otp", "mfa", "urn:openai:amr:otp_email"],
        "at_hash": hashlib.sha256(access_token.encode("utf-8")).hexdigest()[:22],
        "aud": ["app_EMoamEEZ73f0CkXaXp7hrann"],
        "auth_provider": "password",
        "auth_time": auth_time,
        "email": email_from_token,
        "email_verified": email_verified,
        "exp": exp,
        "https://api.openai.com/auth": compat_auth,
        "iat": iat,
        "iss": payload.get("iss") or "https://auth.openai.com",
        "jti": f"compat-{hashlib.sha1(access_token.encode('utf-8')).hexdigest()[:32]}",
        "name": _derive_display_name(email_from_token),
        "rat": auth_time,
        "sid": session_id,
        "sub": payload.get("sub") or user_id,
    }

    header = {
        "alg": "RS256",
        "typ": "JWT",
        "kid": "compat",
    }
    signature = _b64url_bytes(b"compat_signature_for_cpa_parsing_only")
    return f"{_b64url_json(header)}.{_b64url_json(compat_payload)}.{signature}"


def _get_config_value(key: str) -> str:
    try:
        from core.config_store import config_store
        return config_store.get(key, "")
    except Exception:
        return ""


def generate_token_json(account) -> dict:
    """
    生成 CPA 格式的 Token JSON。
    接受任意 duck-typed 对象（需有 email, access_token, refresh_token 属性），
    expired / account_id 从 JWT 自动解码，与 chatgpt_register 逻辑一致。
    """
    email = getattr(account, "email", "")
    access_token = getattr(account, "access_token", "")
    refresh_token = getattr(account, "refresh_token", "")
    id_token = getattr(account, "id_token", "")
    if access_token and not id_token:
        id_token = _build_compat_id_token(access_token=access_token, email=email)

    expired_str = ""
    account_id = ""
    if access_token:
        payload = _decode_jwt_payload(access_token)
        auth_info = _get_auth_info(payload)
        account_id = auth_info.get("chatgpt_account_id", "")
        exp_timestamp = payload.get("exp")
        if isinstance(exp_timestamp, int) and exp_timestamp > 0:
            exp_dt = datetime.fromtimestamp(
                exp_timestamp, tz=timezone(timedelta(hours=8)))
            expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    now = datetime.now(tz=timezone(timedelta(hours=8)))
    return {
        "type": "codex",
        "email": email,
        "expired": expired_str,
        "id_token": id_token,
        "account_id": account_id,
        "access_token": access_token,
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "refresh_token": refresh_token,
    }


def _default_token_output_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "account"


def save_token_json_file(token_data: dict, output_dir: str | Path | None = None) -> Path:
    email = str(token_data.get("email", "") or "").strip()
    if not email:
        raise ValueError("token_data 缺少 email，无法生成导出文件")

    target_dir = Path(output_dir) if output_dir else _default_token_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{email}.json"
    output_path.write_text(
        json.dumps(token_data, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def upload_to_cpa(
    token_data: dict,
    api_url: str = None,
    api_key: str = None,
    proxy: str = None,
) -> Tuple[bool, str]:
    """上传单个账号到 CPA 管理平台（不走代理）。
    api_url / api_key 为空时自动从 ConfigStore 读取。"""
    if not api_url:
        api_url = _get_config_value("cpa_api_url")
    if not api_key:
        api_key = _get_config_value("cpa_api_key")
    if not api_url:
        return False, "CPA API URL 未配置"

    upload_url = f"{api_url.rstrip('/')}/v0/management/auth-files"

    filename = f"{token_data['email']}.json"
    file_content = json.dumps(token_data, ensure_ascii=False, indent=2).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key or ''}",
    }

    mime = None
    try:
        mime = CurlMime()
        mime.addpart(
            name="file",
            data=file_content,
            filename=filename,
            content_type="application/json",
        )

        response = cffi_requests.post(
            upload_url,
            multipart=mime,
            headers=headers,
            proxies=None,
            verify=False,
            timeout=30,
            impersonate="chrome110",
        )

        if response.status_code in (200, 201):
            return True, "上传成功"

        error_msg = f"上传失败: HTTP {response.status_code}"
        try:
            error_detail = response.json()
            if isinstance(error_detail, dict):
                error_msg = error_detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {response.text[:200]}"
        return False, error_msg

    except Exception as e:
        logger.error(f"CPA 上传异常: {e}")
        return False, f"上传异常: {str(e)}"
    finally:
        if mime:
            mime.close()


def upload_to_team_manager(
    account,
    api_url: str = None,
    api_key: str = None,
) -> Tuple[bool, str]:
    """上传单账号到 Team Manager（直连，不走代理）。
    api_url / api_key 为空时自动从 ConfigStore 读取。"""
    if not api_url:
        api_url = _get_config_value("team_manager_url")
    if not api_key:
        api_key = _get_config_value("team_manager_key")
    if not api_url:
        return False, "Team Manager API URL 未配置"
    if not api_key:
        return False, "Team Manager API Key 未配置"

    email = getattr(account, "email", "")
    access_token = getattr(account, "access_token", "")
    if not access_token:
        return False, "账号缺少 access_token"

    url = api_url.rstrip("/") + "/api/accounts/import"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "import_type": "single",
        "email": email,
        "access_token": access_token,
        "session_token": getattr(account, "session_token", ""),
        "refresh_token": getattr(account, "refresh_token", ""),
        "client_id": getattr(account, "client_id", ""),
    }

    try:
        resp = cffi_requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=None,
            verify=False,
            timeout=30,
            impersonate="chrome110",
        )
        if resp.status_code in (200, 201):
            return True, "上传成功"
        error_msg = f"上传失败: HTTP {resp.status_code}"
        try:
            detail = resp.json()
            if isinstance(detail, dict):
                error_msg = detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {resp.text[:200]}"
        return False, error_msg
    except Exception as e:
        logger.error(f"Team Manager 上传异常: {e}")
        return False, f"上传异常: {str(e)}"


def upload_to_codex_proxy(
    account,
    api_url: str = None,
    api_key: str = None,
) -> Tuple[bool, str]:
    """上传单账号到 CodexProxy（通过 refresh_token，不走代理）。
    api_url / api_key 为空时自动从 ConfigStore 读取。"""
    if not api_url:
        api_url = _get_config_value("codex_proxy_url")
    if not api_key:
        api_key = _get_config_value("codex_proxy_key")
    if not api_url:
        return False, "CodexProxy API URL 未配置"
    if not api_key:
        return False, "CodexProxy Admin Key 未配置"

    refresh_token = getattr(account, "refresh_token", "")
    if not refresh_token:
        return False, "账号缺少 refresh_token"

    url = api_url.rstrip("/") + "/api/admin/accounts"
    headers = {
        "x-admin-key": api_key,
        "Content-Type": "application/json",
        "accept": "*/*",
    }
    payload = {
        "refresh_token": refresh_token,
        "proxy_url": "",
    }

    try:
        resp = cffi_requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=None,
            verify=False,
            timeout=30,
            impersonate="chrome110",
        )
        if resp.status_code in (200, 201):
            try:
                data = resp.json()
                msg = data.get("message", "上传成功")
            except Exception:
                msg = "上传成功"
            return True, msg
        error_msg = f"上传失败: HTTP {resp.status_code}"
        try:
            detail = resp.json()
            if isinstance(detail, dict):
                error_msg = detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {resp.text[:200]}"
        return False, error_msg
    except Exception as e:
        logger.error(f"CodexProxy 上传异常: {e}")
        return False, f"上传异常: {str(e)}"


def upload_at_to_codex_proxy(
    account,
    api_url: str = None,
    api_key: str = None,
) -> Tuple[bool, str]:
    """上传单账号到 CodexProxy（通过 access_token，走 /api/admin/accounts/at）。"""
    if not api_url:
        api_url = _get_config_value("codex_proxy_url")
    if not api_key:
        api_key = _get_config_value("codex_proxy_key")
    if not api_url:
        return False, "CodexProxy API URL 未配置"
    if not api_key:
        return False, "CodexProxy Admin Key 未配置"

    access_token = getattr(account, "access_token", "")
    if not access_token:
        return False, "账号缺少 access_token"

    url = api_url.rstrip("/") + "/api/admin/accounts/at"
    headers = {
        "x-admin-key": api_key,
        "Content-Type": "application/json",
        "accept": "*/*",
    }
    payload = {
        "access_token": access_token,
        "proxy_url": "",
    }

    try:
        resp = cffi_requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=None,
            verify=False,
            timeout=30,
            impersonate="chrome110",
        )
        if resp.status_code in (200, 201):
            try:
                data = resp.json()
                msg = data.get("message", "上传成功")
            except Exception:
                msg = "上传成功"
            return True, msg
        error_msg = f"上传失败: HTTP {resp.status_code}"
        try:
            detail = resp.json()
            if isinstance(detail, dict):
                error_msg = detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {resp.text[:200]}"
        return False, error_msg
    except Exception as e:
        logger.error(f"CodexProxy AT 上传异常: {e}")
        return False, f"上传异常: {str(e)}"


def test_cpa_connection(api_url: str, api_token: str, proxy: str = None) -> Tuple[bool, str]:
    """测试 CPA 连接（不走代理）"""
    if not api_url:
        return False, "API URL 不能为空"
    if not api_token:
        return False, "API Token 不能为空"

    api_url = api_url.rstrip("/")
    test_url = f"{api_url}/v0/management/auth-files"
    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        response = cffi_requests.options(
            test_url,
            headers=headers,
            proxies=None,
            verify=False,
            timeout=10,
            impersonate="chrome110",
        )

        if response.status_code in (200, 204, 401, 403, 405):
            if response.status_code == 401:
                return False, "连接成功，但 API Token 无效"
            return True, "CPA 连接测试成功"

        return False, f"服务器返回异常状态码: {response.status_code}"

    except cffi_requests.exceptions.ConnectionError as e:
        return False, f"无法连接到服务器: {str(e)}"
    except cffi_requests.exceptions.Timeout:
        return False, "连接超时，请检查网络配置"
    except Exception as e:
        return False, f"连接测试失败: {str(e)}"
