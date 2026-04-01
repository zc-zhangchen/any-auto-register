"""平台操作 API - 通用接口，各平台通过 get_platform_actions/execute_action 实现"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
import json
from typing import Any
from core.db import AccountModel, get_session
from core.registry import get
from core.base_platform import RegisterConfig
from core.config_store import config_store
from services.chatgpt_account_state import apply_chatgpt_status_policy
from services.chatgpt_sync import update_account_model_cliproxy_sync

router = APIRouter(prefix="/actions", tags=["actions"])


class ActionRequest(BaseModel):
    params: dict = {}


class BatchActionRequest(BaseModel):
    account_ids: list[int] = []
    all_filtered: bool = False
    email: str = ""
    status: str = ""
    params: dict = {}


def _merge_extra_patch(base: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_extra_patch(base[key], value)
        else:
            base[key] = value
    return base


def _to_platform_account(acc_model: AccountModel):
    from core.base_platform import Account, AccountStatus

    return Account(
        platform=acc_model.platform,
        email=acc_model.email,
        password=acc_model.password,
        user_id=acc_model.user_id,
        token=acc_model.token,
        status=AccountStatus(acc_model.status),
        extra=acc_model.get_extra(),
    )


def _apply_action_result(
    platform: str,
    action_id: str,
    acc_model: AccountModel,
    result: dict[str, Any],
    session: Session,
) -> None:
    if platform == "chatgpt":
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        status_reason = ""
        if action_id == "probe_local_status":
            status_reason = apply_chatgpt_status_policy(acc_model, local_probe=data.get("probe"))
        elif action_id == "sync_cliproxyapi_status":
            status_reason = apply_chatgpt_status_policy(acc_model, remote_sync=data.get("sync"))
        if status_reason:
            from datetime import datetime, timezone

            acc_model.updated_at = datetime.now(timezone.utc)
            session.add(acc_model)
    if isinstance(result.get("account_extra_patch"), dict):
        extra = acc_model.get_extra()
        _merge_extra_patch(extra, result["account_extra_patch"])
        acc_model.set_extra(extra)
        from datetime import datetime, timezone
        acc_model.updated_at = datetime.now(timezone.utc)
        session.add(acc_model)
    if platform == "chatgpt" and action_id == "upload_cpa":
        from services.chatgpt_sync import update_account_model_cpa_sync

        sync_msg = result.get("data") or result.get("error") or ""
        update_account_model_cpa_sync(
            acc_model,
            bool(result.get("ok")),
            str(sync_msg),
            session=session,
            commit=False,
        )
    if result.get("ok") and result.get("data", {}) and isinstance(result["data"], dict):
        data = result["data"]
        tracked_keys = {"access_token", "accessToken", "refreshToken", "clientId", "clientSecret", "webAccessToken"}
        if tracked_keys.intersection(data.keys()):
            extra = acc_model.get_extra()
            extra.update(data)
            acc_model.set_extra(extra)
            if data.get("access_token"):
                acc_model.token = data["access_token"]
            elif data.get("accessToken"):
                acc_model.token = data["accessToken"]
            from datetime import datetime, timezone

            acc_model.updated_at = datetime.now(timezone.utc)
            session.add(acc_model)


def _execute_platform_action(
    instance: Any,
    platform: str,
    acc_model: AccountModel,
    action_id: str,
    params: dict,
    session: Session,
) -> dict[str, Any]:
    account = _to_platform_account(acc_model)
    result = instance.execute_action(action_id, account, params)
    _apply_action_result(platform, action_id, acc_model, result, session)
    return result


def _resolve_batch_accounts(platform: str, body: BatchActionRequest, session: Session) -> tuple[list[AccountModel], list[int]]:
    if body.account_ids:
        account_ids = []
        seen = set()
        for raw in body.account_ids:
            value = int(raw)
            if value <= 0 or value in seen:
                continue
            seen.add(value)
            account_ids.append(value)

        if not account_ids:
            raise HTTPException(400, "账号 ID 列表不能为空")
        if len(account_ids) > 1000:
            raise HTTPException(400, "单次最多处理 1000 个账号")

        rows = session.exec(
            select(AccountModel)
            .where(AccountModel.platform == platform)
            .where(AccountModel.id.in_(account_ids))
        ).all()
        row_map = {row.id: row for row in rows}
        ordered_rows = [row_map[account_id] for account_id in account_ids if account_id in row_map]
        missing_ids = [account_id for account_id in account_ids if account_id not in row_map]
        return ordered_rows, missing_ids

    if not body.all_filtered:
        raise HTTPException(400, "请提供 account_ids，或指定 all_filtered=true")

    query = select(AccountModel).where(AccountModel.platform == platform)
    if body.status:
        query = query.where(AccountModel.status == body.status)
    if body.email:
        query = query.where(AccountModel.email.contains(body.email))

    rows = session.exec(query).all()
    if len(rows) > 1000:
        raise HTTPException(400, "单次最多处理 1000 个账号")
    return rows, []


def _result_message(result: dict[str, Any]) -> str:
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("message", "detail", "url", "checkout_url", "cashier_url"):
            value = str(data.get(key) or "").strip()
            if value:
                return value
        return json.dumps(data, ensure_ascii=False)
    if str(data or "").strip():
        return str(data)
    return str(result.get("error") or "").strip()


def _execute_batch_cliproxy_sync(accounts: list[AccountModel], session: Session) -> dict[str, Any]:
    from services.cliproxyapi_sync import sync_chatgpt_cliproxyapi_status_batch

    class SyncAccount:
        def __init__(self, model: AccountModel):
            extra = model.get_extra()
            self.id = model.id
            self.email = model.email
            self.user_id = model.user_id
            self.token = model.token
            self.extra = extra
            self.access_token = extra.get("access_token") or model.token
            self.refresh_token = extra.get("refresh_token", "")
            self.id_token = extra.get("id_token", "")
            self.session_token = extra.get("session_token", "")
            self.client_id = extra.get("client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
            self.cookies = extra.get("cookies", "")

    sync_accounts = [SyncAccount(model) for model in accounts]
    sync_results = sync_chatgpt_cliproxyapi_status_batch(sync_accounts)

    items = []
    success_count = 0
    failed_count = 0
    for acc_model in accounts:
        sync_result = sync_results.get(int(acc_model.id or 0), {})
        update_account_model_cliproxy_sync(acc_model, sync_result, session=session, commit=False)
        remote_state = str(sync_result.get("remote_state") or "").strip().lower()
        ok = bool(sync_result.get("uploaded")) and remote_state not in {"unreachable", "not_found"}
        if ok:
            success_count += 1
        else:
            failed_count += 1
        summary = (
            f"远端状态={sync_result.get('status') or 'not_found'}, "
            f"探测={sync_result.get('remote_state') or 'not_checked'}"
        )
        items.append(
            {
                "id": acc_model.id,
                "email": acc_model.email,
                "ok": ok,
                "message": f"CLIProxyAPI 状态同步完成：{summary}",
                "status": acc_model.status,
            }
        )
    return {
        "total": len(items),
        "success": success_count,
        "failed": failed_count,
        "items": items,
    }


@router.get("/{platform}")
def list_actions(platform: str):
    """获取平台支持的操作列表"""
    PlatformCls = get(platform)
    instance = PlatformCls(config=RegisterConfig(extra=config_store.get_all()))
    return {"actions": instance.get_platform_actions()}


@router.post("/{platform}/{action_id}/batch")
def execute_batch_action(
    platform: str,
    action_id: str,
    body: BatchActionRequest,
    session: Session = Depends(get_session),
):
    PlatformCls = get(platform)
    instance = PlatformCls(config=RegisterConfig(extra=config_store.get_all()))
    accounts, missing_ids = _resolve_batch_accounts(platform, body, session)

    if not accounts and not missing_ids:
        return {"total": 0, "success": 0, "failed": 0, "items": []}

    if platform == "chatgpt" and action_id == "sync_cliproxyapi_status":
        batch_result = _execute_batch_cliproxy_sync(accounts, session)
        if missing_ids:
            for missing_id in missing_ids:
                batch_result["failed"] += 1
                batch_result["total"] += 1
                batch_result["items"].append(
                    {
                        "id": missing_id,
                        "email": "",
                        "ok": False,
                        "message": "账号不存在",
                        "status": "",
                    }
                )
        session.commit()
        return batch_result

    items = []
    success_count = 0
    failed_count = 0

    for missing_id in missing_ids:
        failed_count += 1
        items.append(
            {
                "id": missing_id,
                "email": "",
                "ok": False,
                "message": "账号不存在",
                "status": "",
            }
        )

    for acc_model in accounts:
        try:
            result = _execute_platform_action(instance, platform, acc_model, action_id, body.params, session)
            ok = bool(result.get("ok"))
            if ok:
                success_count += 1
            else:
                failed_count += 1
            items.append(
                {
                    "id": acc_model.id,
                    "email": acc_model.email,
                    "ok": ok,
                    "message": _result_message(result),
                    "status": acc_model.status,
                }
            )
        except Exception as exc:
            failed_count += 1
            items.append(
                {
                    "id": acc_model.id,
                    "email": acc_model.email,
                    "ok": False,
                    "message": str(exc),
                    "status": acc_model.status,
                }
            )

    session.commit()
    return {
        "total": len(items),
        "success": success_count,
        "failed": failed_count,
        "items": items,
    }


@router.post("/{platform}/{account_id}/{action_id}")
def execute_action(
    platform: str,
    account_id: int,
    action_id: str,
    body: ActionRequest,
    session: Session = Depends(get_session),
):
    """执行平台特定操作"""
    acc_model = session.get(AccountModel, account_id)
    if not acc_model or acc_model.platform != platform:
        raise HTTPException(404, "账号不存在")

    PlatformCls = get(platform)
    instance = PlatformCls(config=RegisterConfig(extra=config_store.get_all()))

    try:
        result = _execute_platform_action(instance, platform, acc_model, action_id, body.params, session)
        session.commit()
        return result
    except NotImplementedError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        return {"ok": False, "error": str(e)}
