from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config_store import config_store

router = APIRouter(prefix="/contribution", tags=["contribution"])

DEFAULT_CONTRIBUTION_SERVER_URL = "http://new.xem8k5.top:7317/"
SERVER_STATS_CANDIDATES: list[tuple[str, str]] = [
    ("GET", "/public/quota-stats"),
    ("GET", "/public/quota/stats"),
    ("POST", "/public/quota-stats"),
    ("POST", "/public/quota/stats"),
]
KEY_INFO_CANDIDATES: list[tuple[str, str]] = [
    ("GET", "/public/key-info"),
    ("GET", "/public/key/info"),
    ("POST", "/public/key-info"),
    ("POST", "/public/key/info"),
]
REDEEM_CANDIDATES: list[tuple[str, str]] = [
    ("POST", "/public/redeem"),
    ("POST", "/api/contribution/redeem"),
]


class ContributionProxyRequest(BaseModel):
    server_url: str | None = None
    key: str | None = None


class ContributionRedeemRequest(ContributionProxyRequest):
    amount_usd: float = Field(..., gt=0)


class ContributionGenerateKeyRequest(BaseModel):
    server_url: str | None = None
    name: str | None = None


def _resolve_server_url(server_url: str | None) -> str:
    raw = str(server_url or config_store.get("contribution_server_url", "") or "").strip()
    if not raw:
        raw = DEFAULT_CONTRIBUTION_SERVER_URL
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/") + "/"


def _resolve_key(key: str | None) -> str:
    resolved = str(key or config_store.get("contribution_key", "") or "").strip()
    if resolved:
        return resolved
    raise HTTPException(status_code=400, detail="请先配置贡献 key")


def _resolve_key_optional(key: str | None) -> str:
    return str(key or config_store.get("contribution_key", "") or "").strip()


def _request_json(
    method: str,
    server_url: str,
    endpoint: str,
    key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if key:
        headers["X-Public-Key"] = key
        headers["Authorization"] = f"Bearer {key}"
    url = urljoin(server_url, endpoint.lstrip("/"))
    request_kwargs: dict[str, Any] = {
        "method": method.upper(),
        "url": url,
        "timeout": 15,
    }
    if headers:
        request_kwargs["headers"] = headers
    if payload is not None:
        request_kwargs["json"] = payload

    try:
        response = requests.request(**request_kwargs)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"连接贡献服务器失败: {exc}") from exc

    data: Any
    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if response.status_code >= 400:
        detail: Any = data
        if isinstance(data, dict):
            detail = data.get("detail") or data.get("error") or data.get("message") or data
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("error") or detail.get("code") or json_dumps_safe(detail)
        if not isinstance(detail, str):
            detail = json_dumps_safe(detail)
        raise HTTPException(status_code=response.status_code, detail=detail)

    if isinstance(data, dict):
        return data
    return {"data": data}


def json_dumps_safe(value: Any) -> str:
    try:
        import json

        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


@router.post("/quota-stats")
def get_quota_stats(body: ContributionProxyRequest):
    server_url = _resolve_server_url(body.server_url)
    key = _resolve_key_optional(body.key)
    attempts: list[dict[str, Any]] = []

    server_data: dict[str, Any] | None = None
    server_endpoint = ""
    server_method = ""
    for method, endpoint in SERVER_STATS_CANDIDATES:
        try:
            server_data = _request_json(method, server_url, endpoint)
            server_endpoint = endpoint
            server_method = method
            break
        except HTTPException as exc:
            attempts.append(
                {
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )

    if server_data is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "调用额度统计接口失败，请确认 codex2api 是否已启用该接口",
                "attempts": attempts,
            },
        )

    key_data: dict[str, Any] | None = None
    key_method = ""
    key_endpoint = ""
    key_attempts: list[dict[str, Any]] = []
    if key:
        for method, endpoint in KEY_INFO_CANDIDATES:
            try:
                key_data = _request_json(method, server_url, endpoint, key)
                key_method = method
                key_endpoint = endpoint
                break
            except HTTPException as exc:
                key_attempts.append(
                    {
                        "method": method,
                        "endpoint": endpoint,
                        "status_code": exc.status_code,
                        "detail": exc.detail,
                    }
                )

    response_data: dict[str, Any] = {
        "server_info": server_data,
        "key_info": key_data,
    }

    result: dict[str, Any] = {
        "ok": True,
        "server_method": server_method,
        "server_endpoint": server_endpoint,
        "data": response_data,
    }
    if key:
        result["key_method"] = key_method
        result["key_endpoint"] = key_endpoint
        if key_data is None:
            result["key_error"] = {
                "message": "key 信息接口调用失败",
                "attempts": key_attempts,
            }
    else:
        result["key_error"] = "未配置 key，仅返回服务器额度统计"
    return result


@router.post("/key-info")
def get_key_info(body: ContributionProxyRequest):
    server_url = _resolve_server_url(body.server_url)
    key = _resolve_key(body.key)
    attempts: list[dict[str, Any]] = []

    for method, endpoint in KEY_INFO_CANDIDATES:
        try:
            data = _request_json(method, server_url, endpoint, key)
            return {
                "ok": True,
                "method": method,
                "endpoint": endpoint,
                "data": data,
            }
        except HTTPException as exc:
            attempts.append(
                {
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )

    raise HTTPException(
        status_code=502,
        detail={
            "message": "调用 key 信息接口失败，请确认 codex2api 是否已启用该接口",
            "attempts": attempts,
        },
    )


@router.post("/redeem")
def redeem(body: ContributionRedeemRequest):
    server_url = _resolve_server_url(body.server_url)
    key = _resolve_key(body.key)
    attempts: list[dict[str, Any]] = []
    data: dict[str, Any] | None = None
    endpoint_hit = ""

    for method, endpoint in REDEEM_CANDIDATES:
        try:
            data = _request_json(
                method,
                server_url,
                endpoint,
                key,
                payload={"amount_usd": body.amount_usd},
            )
            endpoint_hit = endpoint
            break
        except HTTPException as exc:
            attempts.append(
                {
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )

    if data is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "调用提现接口失败，请确认 codex2api 是否已启用 /public/redeem",
                "attempts": attempts,
            },
        )

    redeemed_amount = data.get("redeemed_amount_usd")
    redeem_code = data.get("code")
    return {
        "ok": True,
        "endpoint": endpoint_hit or "/public/redeem",
        "redeemed_amount_usd": redeemed_amount,
        "code": redeem_code,
        "message": f"提现成功！额度：{redeemed_amount if redeemed_amount is not None else '-'} 兑换码：{redeem_code or '-'}",
        "data": data,
    }


@router.post("/generate-key")
def generate_key(body: ContributionGenerateKeyRequest):
    server_url = _resolve_server_url(body.server_url)
    payload: dict[str, Any] | None = None
    name = str(body.name or "").strip()
    if name:
        payload = {"name": name}

    data = _request_json(
        "POST",
        server_url,
        "/public/generate",
        payload=payload,
    )
    return {
        "ok": True,
        "endpoint": "/public/generate",
        "data": data,
    }
