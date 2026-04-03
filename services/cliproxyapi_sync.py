"""CLIProxyAPI 只读状态同步。"""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from platforms.chatgpt.status_probe import CODEX_USER_AGENT, extract_chatgpt_account_id
from services.chatgpt_account_state import is_account_deactivated_message

DEFAULT_CLIPROXYAPI_BASE_URL = "http://127.0.0.1:8317"
SYNC_RETRY_ATTEMPTS = 3
SYNC_RETRY_DELAY_SECONDS = 0.4
BATCH_PROBE_DELAY_SECONDS = 0.12

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_config_value(key: str, default: str = "") -> str:
    try:
        from core.config_store import config_store

        value = str(config_store.get(key, "") or "").strip()
        return value or default
    except Exception:
        return default


def _base_url(api_url: str | None = None) -> str:
    return str(api_url or _get_config_value("cliproxyapi_base_url", DEFAULT_CLIPROXYAPI_BASE_URL) or DEFAULT_CLIPROXYAPI_BASE_URL).rstrip("/")


def _api_key(api_key: str | None = None) -> str:
    return str(api_key or _get_config_value("cliproxyapi_management_key", "cliproxyapi") or "cliproxyapi").strip()


def _headers(api_key: str | None = None) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {_api_key(api_key)}",
        "Content-Type": "application/json",
    }


def _parse_json_text(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_header_error_json(headers: dict[str, Any]) -> dict[str, Any]:
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
    return _parse_json_text(decoded)


def _extract_error_code(headers: dict[str, Any], body_json: dict[str, Any], header_error_json: dict[str, Any]) -> str:
    for key in ("X-Openai-Ide-Error-Code", "x-openai-ide-error-code"):
        value = headers.get(key)
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


def _request_json(method: str, path: str, *, api_url: str | None = None, api_key: str | None = None, json_body: dict | None = None) -> Any:
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    target = f"{_base_url(api_url)}{path}"
    try:
        response = requests.request(
            method,
            target,
            headers=_headers(api_key),
            json=json_body,
            timeout=30,
            verify=False,
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"CLIProxyAPI 无法连接，请确认服务已启动或 API URL 是否正确：{_base_url(api_url)}") from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"CLIProxyAPI 请求超时：{_base_url(api_url)}") from exc
    response.raise_for_status()
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return response.text


def _is_retryable_sync_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    markers = (
        "无法连接",
        "请求超时",
        "connection",
        "timeout",
        "timed out",
    )
    return any(marker in text for marker in markers)


def _retry_sync_call(func, *, attempts: int = SYNC_RETRY_ATTEMPTS):
    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _is_retryable_sync_error(exc):
                raise
            time.sleep(SYNC_RETRY_DELAY_SECONDS)
    if last_error is not None:
        raise last_error
    raise RuntimeError("sync retry failed without captured error")


def list_auth_files(*, api_url: str | None = None, api_key: str | None = None) -> list[dict[str, Any]]:
    data = _request_json("GET", "/v0/management/auth-files", api_url=api_url, api_key=api_key)
    files = data.get("files", []) if isinstance(data, dict) else []
    return [item for item in files if isinstance(item, dict)]


def _status_rank(status: str) -> int:
    order = {
        "active": 0,
        "refreshing": 1,
        "pending": 2,
        "error": 3,
        "disabled": 4,
    }
    return order.get(str(status or "").strip().lower(), 9)


def _match_auth_file(account: Any, files: list[dict[str, Any]]) -> dict[str, Any] | None:
    email = str(getattr(account, "email", "") or "").strip().lower()
    if not email:
        return None
    candidates = []
    for item in files:
        provider = str(item.get("provider") or item.get("type") or "").strip().lower()
        item_email = str(item.get("email") or "").strip().lower()
        item_name = str(item.get("name") or "").strip().lower()
        if provider != "codex":
            continue
        if item_email == email or item_name == f"{email}.json":
            candidates.append(item)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            _status_rank(item.get("status", "")),
            str(item.get("updated_at") or item.get("modtime") or item.get("created_at") or ""),
        ),
        reverse=False,
    )
    return candidates[0]


def _probe_remote_auth(auth_index: str, account_id: str, *, api_url: str | None = None, api_key: str | None = None) -> dict[str, Any]:
    checked_at = _utcnow_iso()
    if not auth_index:
        return {
            "last_probe_at": checked_at,
            "last_probe_status_code": 0,
            "last_probe_error_code": "",
            "last_probe_message": "缺少 auth_index，无法探测远端额度状态",
            "remote_state": "probe_skipped",
        }
    if not account_id:
        return {
            "last_probe_at": checked_at,
            "last_probe_status_code": 0,
            "last_probe_error_code": "",
            "last_probe_message": "缺少 Chatgpt-Account-Id，无法严格探测远端额度状态",
            "remote_state": "probe_skipped",
        }

    data = _request_json(
        "POST",
        "/v0/management/api-call",
        api_url=api_url,
        api_key=api_key,
        json_body={
            "authIndex": auth_index,
            "method": "GET",
            "url": "https://chatgpt.com/backend-api/wham/usage",
            "header": {
                "Authorization": "Bearer $TOKEN$",
                "Content-Type": "application/json",
                "User-Agent": CODEX_USER_AGENT,
                "Chatgpt-Account-Id": account_id,
            },
        },
    )

    upstream_status = int((data or {}).get("status_code") or 0)
    headers = (data or {}).get("header") or {}
    body_text = str((data or {}).get("body") or "")
    body_json = _parse_json_text(body_text)
    header_error_json = _parse_header_error_json(headers)
    error_code = _extract_error_code(headers, body_json, header_error_json)
    message = _extract_error_message(body_json, header_error_json, body_text, upstream_status)

    remote_state = "probe_failed"
    if upstream_status == 200:
        remote_state = "usable"
    elif upstream_status == 401:
        remote_state = "access_token_invalidated" if error_code == "token_invalidated" else "unauthorized"
    elif is_account_deactivated_message(error_code, message):
        remote_state = "account_deactivated"
    elif upstream_status in (402, 403):
        remote_state = "payment_required"
    elif upstream_status == 429:
        remote_state = "quota_exhausted"

    return {
        "last_probe_at": checked_at,
        "last_probe_status_code": upstream_status,
        "last_probe_error_code": error_code,
        "last_probe_message": message,
        "remote_state": remote_state,
    }


def _build_remote_sync_result(
    account: Any,
    matched: dict[str, Any] | None,
    synced_at: str,
    *,
    api_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    if not matched:
        return {
            "uploaded": False,
            "last_synced_at": synced_at,
            "message": "未在 CLIProxyAPI 找到匹配的 Codex auth-file",
            "remote_state": "not_found",
            "base_url": _base_url(api_url),
        }

    account_id = extract_chatgpt_account_id(account)
    remote = {
        "uploaded": True,
        "last_synced_at": synced_at,
        "message": "",
        "base_url": _base_url(api_url),
        "auth_index": str(matched.get("auth_index") or "").strip(),
        "name": str(matched.get("name") or "").strip(),
        "provider": str(matched.get("provider") or matched.get("type") or "").strip(),
        "status": str(matched.get("status") or "").strip(),
        "status_message": str(matched.get("status_message") or "").strip(),
        "unavailable": bool(matched.get("unavailable")),
        "disabled": bool(matched.get("disabled")),
        "last_refresh": str(matched.get("last_refresh") or "").strip(),
        "next_retry_after": str(matched.get("next_retry_after") or "").strip(),
        "remote_plan_type": str(((matched.get("id_token") or {}).get("plan_type") if isinstance(matched.get("id_token"), dict) else "") or "").strip(),
        "chatgpt_subscription_active_until": str(((matched.get("id_token") or {}).get("chatgpt_subscription_active_until") if isinstance(matched.get("id_token"), dict) else "") or "").strip(),
    }
    try:
        remote.update(
            _retry_sync_call(
                lambda: _probe_remote_auth(remote["auth_index"], account_id, api_url=api_url, api_key=api_key)
            )
        )
    except Exception as exc:
        remote.update(
            {
                "last_probe_at": synced_at,
                "last_probe_status_code": 0,
                "last_probe_error_code": "",
                "last_probe_message": str(exc),
                "remote_state": "unreachable",
                "message": str(exc),
            }
        )
        return remote
    if remote["status"] == "error" and remote["status_message"]:
        remote["message"] = remote["status_message"]
    elif remote["last_probe_message"]:
        remote["message"] = remote["last_probe_message"]
    return remote


def sync_chatgpt_cliproxyapi_status(
    account: Any,
    *,
    api_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    synced_at = _utcnow_iso()
    try:
        files = _retry_sync_call(lambda: list_auth_files(api_url=api_url, api_key=api_key))
    except Exception as exc:
        return {
            "uploaded": False,
            "last_synced_at": synced_at,
            "message": str(exc),
            "remote_state": "unreachable",
            "base_url": _base_url(api_url),
        }
    matched = _match_auth_file(account, files)
    return _build_remote_sync_result(account, matched, synced_at, api_url=api_url, api_key=api_key)


def sync_chatgpt_cliproxyapi_status_batch(
    accounts: list[Any],
    *,
    api_url: str | None = None,
    api_key: str | None = None,
) -> dict[int, dict[str, Any]]:
    synced_at = _utcnow_iso()
    results: dict[int, dict[str, Any]] = {}
    if not accounts:
        return results

    try:
        files = _retry_sync_call(lambda: list_auth_files(api_url=api_url, api_key=api_key))
    except Exception as exc:
        fallback = {
            "uploaded": False,
            "last_synced_at": synced_at,
            "message": str(exc),
            "remote_state": "unreachable",
            "base_url": _base_url(api_url),
        }
        for account in accounts:
            account_id = getattr(account, "id", None)
            if account_id is not None:
                results[int(account_id)] = dict(fallback)
        logger.warning("CLIProxyAPI 批量同步失败：无法获取 auth-files, accounts=%s, error=%s", len(accounts), exc)
        return results

    for index, account in enumerate(accounts):
        account_id = getattr(account, "id", None)
        if account_id is None:
            continue
        matched = _match_auth_file(account, files)
        results[int(account_id)] = _build_remote_sync_result(account, matched, synced_at, api_url=api_url, api_key=api_key)
        if index < len(accounts) - 1 and matched:
            time.sleep(BATCH_PROBE_DELAY_SECONDS)

    unreachable = sum(1 for item in results.values() if str(item.get("remote_state") or "").strip().lower() == "unreachable")
    not_found = sum(1 for item in results.values() if str(item.get("remote_state") or "").strip().lower() == "not_found")
    logger.info(
        "CLIProxyAPI 批量同步完成：accounts=%s, unreachable=%s, not_found=%s, base_url=%s",
        len(results),
        unreachable,
        not_found,
        _base_url(api_url),
    )
    return results
