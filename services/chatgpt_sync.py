"""ChatGPT 账号与 CPA 的同步辅助逻辑。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from core.db import AccountModel, engine

CPA_SYNC_NAME = "cpa"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _get_account_extra(account: Any) -> dict[str, Any]:
    if hasattr(account, "get_extra"):
        try:
            extra = account.get_extra()
            if isinstance(extra, dict):
                return extra
        except Exception:
            pass
    extra = getattr(account, "extra", {})
    return extra if isinstance(extra, dict) else {}


def get_cpa_sync_state(extra_or_account: Any) -> dict[str, Any]:
    extra = extra_or_account if isinstance(extra_or_account, dict) else _get_account_extra(extra_or_account)
    sync_statuses = extra.get("sync_statuses", {})
    if not isinstance(sync_statuses, dict):
        return {}
    state = sync_statuses.get(CPA_SYNC_NAME, {})
    return state if isinstance(state, dict) else {}


def has_cpa_upload_success(extra_or_account: Any) -> bool:
    state = get_cpa_sync_state(extra_or_account)
    return bool(state.get("uploaded") or state.get("uploaded_at"))


def record_cpa_sync_result(extra: dict[str, Any], ok: bool, msg: str) -> dict[str, Any]:
    sync_statuses = extra.get("sync_statuses")
    if not isinstance(sync_statuses, dict):
        sync_statuses = {}

    state = sync_statuses.get(CPA_SYNC_NAME)
    if not isinstance(state, dict):
        state = {}

    now = _utcnow_iso()
    state["last_attempt_ok"] = bool(ok)
    state["last_message"] = msg
    state["last_attempt_at"] = now
    state["uploaded"] = bool(state.get("uploaded")) or bool(ok)
    if ok:
        state["uploaded_at"] = now

    sync_statuses[CPA_SYNC_NAME] = state
    extra["sync_statuses"] = sync_statuses
    return state


def build_chatgpt_sync_account(account: Any):
    extra = _get_account_extra(account)

    class _SyncAccount:
        pass

    obj = _SyncAccount()
    obj.email = getattr(account, "email", "")
    obj.access_token = extra.get("access_token") or getattr(account, "token", "")
    obj.refresh_token = extra.get("refresh_token", "")
    obj.id_token = extra.get("id_token", "")
    obj.session_token = extra.get("session_token", "")
    obj.client_id = extra.get("client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
    obj.cookies = extra.get("cookies", "")
    return obj


def upload_chatgpt_account_to_cpa(account: Any, api_url: str | None = None, api_key: str | None = None) -> tuple[bool, str]:
    try:
        sync_account = build_chatgpt_sync_account(account)
        if not getattr(sync_account, "access_token", ""):
            return False, "账号缺少 access_token"

        from platforms.chatgpt.cpa_upload import generate_token_json, upload_to_cpa

        token_data = generate_token_json(sync_account)
        return upload_to_cpa(token_data, api_url=api_url, api_key=api_key)
    except Exception as exc:
        return False, f"上传异常: {exc}"


def update_account_model_cpa_sync(
    account: AccountModel,
    ok: bool,
    msg: str,
    session: Session | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    extra = account.get_extra()
    state = record_cpa_sync_result(extra, ok, msg)
    account.set_extra(extra)
    account.updated_at = _utcnow()
    if session is not None:
        session.add(account)
        if commit:
            session.commit()
            session.refresh(account)
    return state


def persist_cpa_sync_result(account: Any, ok: bool, msg: str) -> None:
    if isinstance(account, AccountModel) and account.id is not None:
        with Session(engine) as session:
            row = session.get(AccountModel, account.id)
            if row:
                update_account_model_cpa_sync(row, ok, msg, session=session, commit=True)
                return

    extra = getattr(account, "extra", None)
    if isinstance(extra, dict):
        record_cpa_sync_result(extra, ok, msg)


def upload_account_model_to_cpa(
    account: AccountModel,
    session: Session | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
    commit: bool = True,
) -> tuple[bool, str]:
    ok, msg = upload_chatgpt_account_to_cpa(account, api_url=api_url, api_key=api_key)
    update_account_model_cpa_sync(account, ok, msg, session=session, commit=commit)
    return ok, msg
