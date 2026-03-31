"""ChatGPT 专用功能 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional
from core.db import AccountModel, get_session
import json, sys


router = APIRouter(prefix="/chatgpt", tags=["chatgpt"])

COUNTRIES = ["SG", "US", "TR", "JP", "HK", "GB", "AU", "CA", "IN", "BR", "MX"]


class UploadRequest(BaseModel):
    account_ids: list[int]
    cpa_api_url: Optional[str] = None
    cpa_api_token: Optional[str] = None
    team_manager_url: Optional[str] = None
    team_manager_key: Optional[str] = None


def _get_account(account_id: int, session: Session) -> AccountModel:
    acc = session.get(AccountModel, account_id)
    if not acc or acc.platform != "chatgpt":
        raise HTTPException(404, "账号不存在")
    return acc


def _to_codex_account(acc: AccountModel):
    """转换为 codex-register 的 Account 对象（duck-typing）"""
    extra = acc.get_extra()

    class _Acc:
        pass

    a = _Acc()
    a.email = acc.email
    a.access_token = extra.get("access_token") or acc.token
    a.refresh_token = extra.get("refresh_token", "")
    a.id_token = extra.get("id_token", "")
    a.session_token = extra.get("session_token", "")
    a.client_id = extra.get("client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
    a.cookies = extra.get("cookies", "")
    return a


# ── Token 刷新 ──────────────────────────────────────────────
@router.post("/{account_id}/refresh-token")
def refresh_token(account_id: int, proxy: Optional[str] = None,
                  session: Session = Depends(get_session)):
    acc = _get_account(account_id, session)
    codex_acc = _to_codex_account(acc)

    from platforms.chatgpt.token_refresh import TokenRefreshManager
    manager = TokenRefreshManager(proxy_url=proxy)
    result = manager.refresh_account(codex_acc)

    if result.success:
        extra = acc.get_extra()
        extra["access_token"] = result.access_token
        if result.refresh_token:
            extra["refresh_token"] = result.refresh_token
        acc.set_extra(extra)
        acc.token = result.access_token
        from datetime import datetime
        acc.updated_at = datetime.utcnow()
        session.add(acc)
        session.commit()
        return {"ok": True, "access_token": result.access_token[:40] + "..."}
    raise HTTPException(400, result.error_message)


# ── 生成支付链接 ────────────────────────────────────────────
class PaymentReq(BaseModel):
    plan: str = "plus"  # plus | team
    country: str = "SG"
    proxy: Optional[str] = None
    workspace_name: str = "MyTeam"
    seat_quantity: int = 5
    price_interval: str = "month"


@router.post("/{account_id}/payment-link")
def generate_payment_link(account_id: int, req: PaymentReq,
                          session: Session = Depends(get_session)):
    acc = _get_account(account_id, session)
    codex_acc = _to_codex_account(acc)

    from platforms.chatgpt.payment import generate_plus_link, generate_team_link
    if req.plan == "plus":
        url = generate_plus_link(codex_acc, proxy=req.proxy, country=req.country)
    else:
        url = generate_team_link(
            codex_acc, workspace_name=req.workspace_name,
            price_interval=req.price_interval, seat_quantity=req.seat_quantity,
            proxy=req.proxy, country=req.country
        )
    return {"url": url, "plan": req.plan, "country": req.country}


# ── 检查订阅状态 ────────────────────────────────────────────
@router.get("/{account_id}/subscription")
def check_subscription(account_id: int, proxy: Optional[str] = None,
                       session: Session = Depends(get_session)):
    acc = _get_account(account_id, session)
    codex_acc = _to_codex_account(acc)

    from platforms.chatgpt.payment import check_subscription_status
    status = check_subscription_status(codex_acc, proxy=proxy)

    # 更新账号状态
    acc.status = status
    from datetime import datetime
    acc.updated_at = datetime.utcnow()
    session.add(acc)
    session.commit()
    return {"subscription": status, "email": acc.email}


# ── CPA 上传 ────────────────────────────────────────────────
class CpaUploadReq(BaseModel):
    api_url: str
    api_key: str = ""


@router.post("/{account_id}/upload-cpa")
def upload_cpa(account_id: int, req: CpaUploadReq,
               session: Session = Depends(get_session)):
    acc = _get_account(account_id, session)
    codex_acc = _to_codex_account(acc)

    from platforms.chatgpt.cpa_upload import upload_to_cpa, generate_token_json
    token_data = generate_token_json(codex_acc)
    ok, msg = upload_to_cpa(token_data, api_url=req.api_url, api_key=req.api_key)
    return {"ok": ok, "message": msg}


class Sub2ApiUploadReq(BaseModel):
    api_url: str
    api_key: str = ""


@router.post("/{account_id}/upload-sub2api")
def upload_sub2api(account_id: int, req: Sub2ApiUploadReq,
                   session: Session = Depends(get_session)):
    acc = _get_account(account_id, session)
    codex_acc = _to_codex_account(acc)

    from platforms.chatgpt.sub2api_upload import upload_to_sub2api

    ok, msg = upload_to_sub2api(
        codex_acc,
        api_url=req.api_url,
        api_key=req.api_key,
    )
    return {"ok": ok, "message": msg}
