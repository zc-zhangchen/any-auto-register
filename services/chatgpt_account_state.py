"""ChatGPT 账号状态判定辅助逻辑。"""

from __future__ import annotations

from typing import Any


INVALID_ACCOUNT_STATUS = "invalid"


def _lower_text(value: Any) -> str:
    return str(value or "").strip().lower()


def is_account_deactivated_message(error_code: Any = "", message: Any = "") -> bool:
    code = _lower_text(error_code)
    text = _lower_text(message)
    if code in {"account_deactivated", "account_deleted"}:
        return True
    markers = (
        "deleted or deactivated",
        "account has been deleted or deactivated",
        "you do not have an account because it has been deleted or deactivated",
    )
    return any(marker in text for marker in markers)


def classify_local_probe_state(probe: dict[str, Any] | None) -> str:
    if not isinstance(probe, dict):
        return ""

    auth = probe.get("auth") if isinstance(probe.get("auth"), dict) else {}
    codex = probe.get("codex") if isinstance(probe.get("codex"), dict) else {}

    auth_state = _lower_text(auth.get("state"))
    auth_status = int(auth.get("http_status") or 0)
    auth_error_code = auth.get("error_code")
    auth_message = auth.get("message")

    if auth_status == 401 or auth_state in {"access_token_invalidated", "unauthorized"}:
        return "auth_401"
    if is_account_deactivated_message(auth_error_code, auth_message):
        return "auth_deactivated"
    if auth_status == 403 and auth_state in {"account_deactivated", "banned_like"}:
        return "auth_403"

    codex_state = _lower_text(codex.get("state"))
    codex_status = int(codex.get("http_status") or 0)
    codex_error_code = codex.get("error_code")
    codex_message = codex.get("message")

    if codex_status == 401 or codex_state in {"access_token_invalidated", "unauthorized"}:
        return "codex_401"
    if is_account_deactivated_message(codex_error_code, codex_message):
        return "codex_deactivated"
    if codex_status == 403 and codex_state == "account_deactivated":
        return "codex_403"

    return ""


def classify_remote_sync_state(sync: dict[str, Any] | None) -> str:
    if not isinstance(sync, dict):
        return ""

    remote_state = _lower_text(sync.get("remote_state"))
    status_code = int(sync.get("last_probe_status_code") or 0)
    error_code = sync.get("last_probe_error_code")
    message = sync.get("last_probe_message") or sync.get("status_message") or sync.get("message")

    if status_code == 401 or remote_state in {"access_token_invalidated", "unauthorized"}:
        return "remote_401"
    if is_account_deactivated_message(error_code, message):
        return "remote_deactivated"
    if status_code == 403 and remote_state in {"account_deactivated", "banned_like"}:
        return "remote_403"

    return ""


def apply_chatgpt_status_policy(
    account: Any,
    *,
    local_probe: dict[str, Any] | None = None,
    remote_sync: dict[str, Any] | None = None,
) -> str:
    reason = classify_local_probe_state(local_probe) or classify_remote_sync_state(remote_sync)
    if reason:
        setattr(account, "status", INVALID_ACCOUNT_STATUS)
    return reason
