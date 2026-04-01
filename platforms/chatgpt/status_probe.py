"""ChatGPT 本地真实状态探测。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from curl_cffi import requests as cffi_requests
from services.chatgpt_account_state import is_account_deactivated_message

CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
CHATGPT_ME_URL = "https://chatgpt.com/backend-api/me"
CODEX_USER_AGENT = "codex_cli_rs/0.116.0 (Mac OS 26.0.1; arm64) Apple_Terminal/464"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_proxies(proxy: Optional[str]) -> Optional[dict[str, str]]:
    if proxy:
        return {"http": proxy, "https": proxy}
    return None


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        parts = str(token or "").split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_auth_info(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("https://api.openai.com/auth", {})
    if isinstance(nested, dict):
        return nested
    return {}


def extract_chatgpt_account_id(account: Any) -> str:
    user_id = str(getattr(account, "user_id", "") or "").strip()
    if user_id:
        return user_id

    extra = getattr(account, "extra", {}) or {}
    id_token = str(extra.get("id_token") or getattr(account, "id_token", "") or "").strip()
    access_token = str(
        extra.get("access_token")
        or getattr(account, "access_token", "")
        or getattr(account, "token", "")
        or ""
    ).strip()

    id_payload = _decode_jwt_payload(id_token)
    auth_info = _extract_auth_info(id_payload)
    account_id = str(auth_info.get("chatgpt_account_id") or auth_info.get("account_id") or "").strip()
    if account_id:
        return account_id

    access_payload = _decode_jwt_payload(access_token)
    auth_info = _extract_auth_info(access_payload)
    return str(auth_info.get("chatgpt_account_id") or auth_info.get("account_id") or "").strip()


def _parse_loose_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_header_error_json(headers: Any) -> dict[str, Any]:
    if not headers:
        return {}
    raw = headers.get("X-Error-Json") or headers.get("x-error-json") or ""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    raw = str(raw or "").strip()
    if not raw:
        return {}
    try:
        decoded = base64.b64decode(raw).decode("utf-8", errors="ignore")
    except Exception:
        return {}
    return _parse_loose_json(decoded)


def _extract_error_code(headers: Any, body_json: dict[str, Any], header_error_json: dict[str, Any]) -> str:
    for key in ("X-Openai-Ide-Error-Code", "x-openai-ide-error-code"):
        value = headers.get(key) if headers else None
        if isinstance(value, list):
            value = value[0] if value else ""
        if str(value or "").strip():
            return str(value).strip()

    candidates = [
        ((body_json.get("error") or {}).get("code") if isinstance(body_json.get("error"), dict) else ""),
        ((header_error_json.get("error") or {}).get("code") if isinstance(header_error_json.get("error"), dict) else ""),
    ]
    for candidate in candidates:
        if str(candidate or "").strip():
            return str(candidate).strip()
    return ""


def _extract_error_message(body_json: dict[str, Any], header_error_json: dict[str, Any], body_text: str, status_code: int) -> str:
    candidates = [
        ((body_json.get("error") or {}).get("message") if isinstance(body_json.get("error"), dict) else ""),
        ((header_error_json.get("error") or {}).get("message") if isinstance(header_error_json.get("error"), dict) else ""),
        body_json.get("message", ""),
        body_text.strip(),
    ]
    for candidate in candidates:
        if str(candidate or "").strip():
            return str(candidate).strip()[:500]
    return f"HTTP {status_code}"


@dataclass
class ProbeHTTPResult:
    status_code: int
    headers: Any
    body_text: str
    body_json: dict[str, Any]
    error_code: str
    message: str


def _perform_get(url: str, headers: dict[str, str], proxy: Optional[str]) -> ProbeHTTPResult:
    response = cffi_requests.get(
        url,
        headers=headers,
        proxies=_build_proxies(proxy),
        timeout=20,
        impersonate="chrome110",
    )
    body_text = response.text or ""
    body_json = _parse_loose_json(body_text)
    header_error_json = _parse_header_error_json(response.headers)
    error_code = _extract_error_code(response.headers, body_json, header_error_json)
    message = _extract_error_message(body_json, header_error_json, body_text, response.status_code)
    return ProbeHTTPResult(
        status_code=response.status_code,
        headers=response.headers,
        body_text=body_text,
        body_json=body_json,
        error_code=error_code,
        message=message,
    )


def _normalize_plan_type(plan_type: str, workspace_plan_type: str) -> str:
    raw = f"{plan_type} {workspace_plan_type}".strip().lower()
    if not raw:
        return "unknown"
    if "enterprise" in raw:
        return "enterprise"
    if "team" in raw:
        return "team"
    if "plus" in raw:
        return "plus"
    if "pro" in raw:
        return "pro"
    if "free" in raw:
        return "free"
    return plan_type.strip().lower() or workspace_plan_type.strip().lower() or "unknown"


def _probe_backend_me(access_token: str, proxy: Optional[str]) -> ProbeHTTPResult:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": CODEX_USER_AGENT,
    }
    return _perform_get(CHATGPT_ME_URL, headers=headers, proxy=proxy)


def _probe_codex_usage(access_token: str, account_id: str, proxy: Optional[str]) -> ProbeHTTPResult:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": CODEX_USER_AGENT,
    }
    if account_id:
        headers["Chatgpt-Account-Id"] = account_id
    return _perform_get(CODEX_USAGE_URL, headers=headers, proxy=proxy)


def probe_local_chatgpt_status(account: Any, proxy: Optional[str] = None) -> dict[str, Any]:
    checked_at = _utcnow_iso()
    extra = getattr(account, "extra", {}) or {}
    access_token = str(
        extra.get("access_token")
        or getattr(account, "access_token", "")
        or getattr(account, "token", "")
        or ""
    ).strip()
    refresh_token = str(extra.get("refresh_token") or getattr(account, "refresh_token", "") or "").strip()
    session_token = str(extra.get("session_token") or getattr(account, "session_token", "") or "").strip()
    account_id = extract_chatgpt_account_id(account)

    result: dict[str, Any] = {
        "version": 1,
        "checked_at": checked_at,
        "auth": {
            "state": "unknown",
            "checked_at": checked_at,
            "source": "backend_me",
            "http_status": 0,
            "error_code": "",
            "message": "",
            "refresh_available": bool(refresh_token or session_token),
        },
        "subscription": {
            "plan": "unknown",
            "checked_at": checked_at,
            "source": "backend_me",
            "workspace_plan_type": "",
            "subscription_active_until": "",
            "chatgpt_account_id": account_id,
        },
        "codex": {
            "state": "not_checked",
            "checked_at": checked_at,
            "source": "wham_usage",
            "http_status": 0,
            "error_code": "",
            "message": "",
            "chatgpt_account_id": account_id,
        },
    }

    if not access_token:
        result["auth"].update(
            {
                "state": "missing_access_token",
                "message": "账号缺少 access_token",
            }
        )
        result["codex"].update(
            {
                "state": "skipped_auth_invalid",
                "message": "缺少 access_token，跳过 Codex 探测",
            }
        )
        return result

    me_result = _probe_backend_me(access_token, proxy=proxy)
    result["auth"].update(
        {
            "http_status": me_result.status_code,
            "error_code": me_result.error_code,
            "message": me_result.message,
        }
    )

    if me_result.status_code == 200 and me_result.body_json:
        body = me_result.body_json
        plan_type = str(body.get("plan_type") or "").strip()
        workspace_plan_type = ""
        orgs = ((body.get("orgs") or {}).get("data") if isinstance(body.get("orgs"), dict) else []) or []
        if isinstance(orgs, list):
            for org in orgs:
                if not isinstance(org, dict):
                    continue
                settings = org.get("settings") or {}
                if isinstance(settings, dict) and str(settings.get("workspace_plan_type") or "").strip():
                    workspace_plan_type = str(settings.get("workspace_plan_type") or "").strip()
                    break

        result["auth"]["state"] = "access_token_valid"
        result["subscription"].update(
            {
                "plan": _normalize_plan_type(plan_type, workspace_plan_type),
                "workspace_plan_type": workspace_plan_type,
                "subscription_active_until": str(
                    body.get("chatgpt_subscription_active_until")
                    or body.get("subscription_active_until")
                    or ""
                ).strip(),
            }
        )

        if not account_id:
            result["codex"].update(
                {
                    "state": "probe_failed",
                    "message": "缺少 Chatgpt-Account-Id，无法严格探测 Codex 状态",
                }
            )
            return result

        codex_result = _probe_codex_usage(access_token, account_id=account_id, proxy=proxy)
        result["codex"].update(
            {
                "http_status": codex_result.status_code,
                "error_code": codex_result.error_code,
                "message": codex_result.message,
            }
        )
        if codex_result.status_code == 200:
            result["codex"]["state"] = "usable"
        elif codex_result.status_code == 401:
            if codex_result.error_code == "token_invalidated":
                result["codex"]["state"] = "access_token_invalidated"
            else:
                result["codex"]["state"] = "unauthorized"
        elif is_account_deactivated_message(codex_result.error_code, codex_result.message):
            result["codex"]["state"] = "account_deactivated"
        elif codex_result.status_code in (402, 403):
            result["codex"]["state"] = "payment_required"
        elif codex_result.status_code == 429:
            result["codex"]["state"] = "quota_exhausted"
        else:
            result["codex"]["state"] = "probe_failed"
        return result

    if me_result.status_code == 401:
        result["auth"]["state"] = (
            "access_token_invalidated"
            if me_result.error_code == "token_invalidated"
            else "unauthorized"
        )
        result["codex"].update(
            {
                "state": "skipped_auth_invalid",
                "message": "本地 access_token 未通过 /backend-api/me 校验，跳过 Codex 探测",
            }
        )
        return result

    if me_result.status_code == 403:
        result["auth"]["state"] = (
            "account_deactivated"
            if is_account_deactivated_message(me_result.error_code, me_result.message)
            else "banned_like"
        )
        result["codex"].update(
            {
                "state": "skipped_auth_invalid",
                "message": "本地 access_token 被拒绝，跳过 Codex 探测",
            }
        )
        return result

    result["auth"]["state"] = "probe_failed"
    result["codex"].update(
        {
            "state": "not_checked",
            "message": "本地认证探测失败，未执行 Codex 探测",
        }
    )
    return result
