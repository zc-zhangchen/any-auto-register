"""iCloud 主号、隐私邮箱与实时收件的 HTTP 接口。"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from platforms.icloud import (
    DEFAULT_ALIAS_LABEL,
    DEFAULT_IMAP_HOST,
    DEFAULT_IMAP_PORT,
    ICloudError,
    LOGIN_STATUS_COMPLETED,
    LoginRequest,
    LoginState,
    SessionImportRequest,
)
from services import icloud_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/icloud", tags=["icloud"])

# 业务错误码到 HTTP 状态码的映射，未列出的按 502 处理。
#
# 这里一律不用 401：401 是面板自己的登录态语义，前端见到就会清 token 跳登录页。
# iCloud 主号的凭据问题是另一回事（是 Apple 那边不认，不是你没登录本面板），
# 用 401 表达会让用户在验证弹窗里点一下保存就被踢出去。
_ERROR_STATUS = {
    "account_not_found": 404,
    "alias_not_found": 404,
    "account_disabled": 409,
    "login_incomplete": 409,
    "login_session_expired": 410,
    "invalid_config": 400,
    "invalid_verification_code": 400,
    "invalid_credentials": 400,
    "session_expired": 409,
    "credentials_unreadable": 409,
    "mail_access_denied": 403,
    "provider_rate_limited": 429,
    # upstream_rejected 是"Apple 收到了并明确拒绝"，属于请求语义问题而不是网关故障。
    # 用 5xx 表达还有个致命副作用：Cloudflare 会把 5xx 的响应体整个换成自己的错误页，
    # 用户只看得到一张 "502 Bad gateway"，Apple 到底说了什么全丢了。
    "upstream_rejected": 422,
    "upstream_error": 502,
    "invalid_response": 502,
    "upstream_unavailable": 503,
}


def _http_error(error: ICloudError) -> HTTPException:
    status = _ERROR_STATUS.get(error.code, 502)
    # 上游失败的原因只存在于响应体里，而反向代理（Cloudflare 等）会把 5xx 的响应体
    # 换成自己的错误页，运维侧就彻底看不到 Apple 到底回了什么。所以这里落一条日志。
    if status >= 500:
        logger.error("iCloud 上游失败 [%s] -> HTTP %s: %s", error.code, status, error)
    return HTTPException(status, str(error))


class LoginStartRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""
    region: str = "global"
    imap_host: str = DEFAULT_IMAP_HOST
    imap_port: int = DEFAULT_IMAP_PORT
    imap_username: str = ""
    imap_password: str = ""


class VerifyCodeRequest(BaseModel):
    code: str


class SendSMSRequest(BaseModel):
    phone_id: int
    mode: str = ""


class CookieImportRequest(BaseModel):
    email: str = ""
    display_name: str = ""
    region: str = "global"
    cookie_header: str = ""
    cookies_json: Any = None
    imap_host: str = DEFAULT_IMAP_HOST
    imap_port: int = DEFAULT_IMAP_PORT
    imap_username: str = ""
    imap_password: str = ""


class AccountUpdateRequest(BaseModel):
    enabled: bool


def _alias_label(label: str, index: int, count: int) -> str:
    """一次生成多个时给标签编号，避免 Apple 那边一串同名地址分不清。"""
    label = label.strip() or DEFAULT_ALIAS_LABEL
    return f"{label} {index}" if count > 1 else label


class GenerateAliasRequest(BaseModel):
    account_id: Optional[int] = None
    account_email: str = ""
    label: str = ""
    note: str = ""
    count: int = Field(default=1, ge=1, le=5)


class BatchDeleteAliasRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    remote: bool = True


def _login_response(state: LoginState) -> dict[str, Any]:
    """登录完成时顺带把主号落库，让前端一次调用即可拿到最终结果。"""
    payload = state.to_dict()
    if state.status == LOGIN_STATUS_COMPLETED:
        payload["account"] = icloud_service.complete_login(state)
    return payload


# ----------------------------------------------------------------- 登录会话


@router.post("/login-sessions")
def start_login(body: LoginStartRequest):
    try:
        return _login_response(
            icloud_service.start_login(
                LoginRequest(
                    email=body.email,
                    password=body.password,
                    display_name=body.display_name,
                    region=body.region,
                    imap_host=body.imap_host,
                    imap_port=body.imap_port,
                    imap_username=body.imap_username,
                    imap_password=body.imap_password,
                )
            )
        )
    except ICloudError as error:
        raise _http_error(error) from error


@router.get("/login-sessions/{login_id}")
def get_login(login_id: str):
    try:
        return icloud_service.login_state(login_id).to_dict()
    except ICloudError as error:
        raise _http_error(error) from error


@router.post("/login-sessions/{login_id}/verify")
def verify_login(login_id: str, body: VerifyCodeRequest):
    try:
        return _login_response(icloud_service.verify_login(login_id, body.code))
    except ICloudError as error:
        raise _http_error(error) from error


@router.post("/login-sessions/{login_id}/resend")
def resend_login_code(login_id: str):
    try:
        return icloud_service.resend_login_code(login_id).to_dict()
    except ICloudError as error:
        raise _http_error(error) from error


@router.post("/login-sessions/{login_id}/sms")
def send_login_sms(login_id: str, body: SendSMSRequest):
    try:
        return icloud_service.send_login_sms(login_id, body.phone_id, body.mode).to_dict()
    except ICloudError as error:
        raise _http_error(error) from error


@router.delete("/login-sessions/{login_id}")
def cancel_login(login_id: str):
    icloud_service.cancel_login(login_id)
    return {"ok": True}


# --------------------------------------------------------------------- 主号


@router.get("/accounts")
def list_accounts():
    return {"items": icloud_service.list_accounts()}


@router.post("/accounts/import-cookie")
def import_cookie(body: CookieImportRequest):
    try:
        return icloud_service.import_session(
            SessionImportRequest(
                region=body.region,
                cookie_header=body.cookie_header,
                cookies_json=body.cookies_json,
                imap_host=body.imap_host,
                imap_port=body.imap_port,
                imap_username=body.imap_username,
                imap_password=body.imap_password,
            ),
            email=body.email,
            display_name=body.display_name,
        )
    except ICloudError as error:
        raise _http_error(error) from error


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, body: AccountUpdateRequest):
    try:
        return icloud_service.set_account_enabled(account_id, body.enabled)
    except ICloudError as error:
        raise _http_error(error) from error


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int):
    try:
        icloud_service.delete_account(account_id)
    except ICloudError as error:
        raise _http_error(error) from error
    return {"ok": True, "account_id": account_id}


@router.post("/accounts/{account_id}/sync")
def sync_account(account_id: int):
    try:
        return icloud_service.sync_aliases(account_id)
    except ICloudError as error:
        raise _http_error(error) from error


@router.get("/accounts/{account_id}/messages")
def account_messages(account_id: int, limit: int = 50, recipient: str = ""):
    try:
        messages = icloud_service.fetch_account_messages(
            account_id, limit=limit, recipient=recipient
        )
    except ICloudError as error:
        raise _http_error(error) from error
    return {"items": [message.to_dict() for message in messages]}


# ----------------------------------------------------------------- 隐私邮箱


@router.get("/aliases")
def list_aliases(account_id: Optional[int] = None):
    return {"items": icloud_service.list_aliases(account_id)}


@router.post("/aliases")
def generate_aliases(body: GenerateAliasRequest):
    try:
        account_id = body.account_id or icloud_service.resolve_account(body.account_email).id
        created = [
            icloud_service.generate_alias(
                account_id, label=_alias_label(body.label, index, body.count), note=body.note
            )
            for index in range(1, body.count + 1)
        ]
    except ICloudError as error:
        raise _http_error(error) from error
    return {"items": created}


@router.post("/aliases/batch-delete")
def batch_delete_aliases(body: BatchDeleteAliasRequest):
    if not body.ids:
        raise HTTPException(400, "请先选择要删除的隐私邮箱")
    result = icloud_service.delete_aliases(body.ids, remote=body.remote)
    return {"ok": not result["failed"], **result}


@router.delete("/aliases/{alias_id}")
def delete_alias(alias_id: int, remote: bool = True):
    try:
        icloud_service.delete_alias(alias_id, remote=remote)
    except ICloudError as error:
        raise _http_error(error) from error
    return {"ok": True, "alias_id": alias_id}


@router.get("/aliases/{alias_id}/messages")
def alias_messages(alias_id: int, limit: int = 50):
    try:
        messages = icloud_service.fetch_alias_messages(alias_id, limit=limit)
    except ICloudError as error:
        raise _http_error(error) from error
    return {"items": [message.to_dict() for message in messages]}
