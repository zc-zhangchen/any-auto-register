"""平台操作 API - 通用接口，各平台通过 get_platform_actions/execute_action 实现"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel
from typing import Any
from core.db import AccountModel, get_session
from core.registry import get
from core.base_platform import RegisterConfig
from core.config_store import config_store

router = APIRouter(prefix="/actions", tags=["actions"])


class ActionRequest(BaseModel):
    params: dict = {}


@router.get("/{platform}")
def list_actions(platform: str):
    """获取平台支持的操作列表"""
    PlatformCls = get(platform)
    instance = PlatformCls(config=RegisterConfig(extra=config_store.get_all()))
    return {"actions": instance.get_platform_actions()}


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

    from core.base_platform import Account, AccountStatus
    account = Account(
        platform=acc_model.platform,
        email=acc_model.email,
        password=acc_model.password,
        user_id=acc_model.user_id,
        token=acc_model.token,
        status=AccountStatus(acc_model.status),
        extra=acc_model.get_extra(),
    )

    try:
        result = instance.execute_action(action_id, account, body.params)
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
        # 若操作返回了新 token，更新数据库
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
        session.commit()
        return result
    except NotImplementedError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        return {"ok": False, "error": str(e)}
