"""Authentication API: password login, JWT session, TOTP 2FA."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json as _json
import os
import secrets
import struct
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


# ── Config helpers ─────────────────────────────────────────────────────────────

def _cfg():
    from core.config_store import config_store
    return config_store


# ── JWT (HS256, stdlib only) ───────────────────────────────────────────────────

def _jwt_secret() -> str:
    env_secret = os.getenv("APP_JWT_SECRET", "")
    if env_secret:
        return env_secret
    stored = _cfg().get("auth_jwt_secret", "")
    if not stored:
        stored = secrets.token_hex(32)
        _cfg().set("auth_jwt_secret", stored)
    return stored


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def create_token(expire_seconds: int = 86400 * 7) -> str:
    header = _b64url_encode(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(_json.dumps({
        "sub": "admin",
        "exp": int(time.time()) + expire_seconds,
        "iat": int(time.time()),
    }).encode())
    sig = _b64url_encode(
        hmac.new(_jwt_secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> dict:
    try:
        header, payload, sig = token.split(".")
    except ValueError:
        raise HTTPException(status_code=401, detail="无效的令牌")
    expected = _b64url_encode(
        hmac.new(_jwt_secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="令牌签名无效")
    try:
        data = _json.loads(_b64url_decode(payload))
    except Exception:
        raise HTTPException(status_code=401, detail="令牌格式错误")
    if data.get("exp", 0) < time.time():
        raise HTTPException(status_code=401, detail="令牌已过期，请重新登录")
    return data


def require_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> None:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未认证")
    verify_token(credentials.credentials)


# ── Password ───────────────────────────────────────────────────────────────────

def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ── TOTP (RFC 6238, stdlib only) ───────────────────────────────────────────────

def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def totp_uri(secret: str, issuer: str = "AccountManager") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}?secret={secret}&issuer={quote(issuer)}"


def _totp_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret.upper())
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


def verify_totp(secret: str, code: str) -> bool:
    counter = int(time.time()) // 30
    user_code = str(code).strip().zfill(6)
    for delta in (-1, 0, 1):
        if hmac.compare_digest(_totp_at(secret, counter + delta), user_code):
            return True
    return False


# ── Pending 2FA sessions (in-memory) ──────────────────────────────────────────

_pending_2fa: dict[str, float] = {}  # temp_token -> expires_at


# ── Schemas ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str


class TotpVerifyRequest(BaseModel):
    temp_token: str
    code: str


class SetupPasswordRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class EnableTotpRequest(BaseModel):
    secret: str
    code: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status")
def auth_status():
    cfg = _cfg()
    return {
        "has_password": bool(cfg.get("auth_password_hash", "")),
        "has_totp": bool(cfg.get("auth_totp_secret", "")),
    }


@router.post("/setup")
def setup_password(
    body: SetupPasswordRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """Set initial password, or update it only when the caller is already authenticated."""
    if not body.password or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 位")
    cfg = _cfg()
    if cfg.get("auth_password_hash", ""):
        if credentials is None:
            raise HTTPException(status_code=401, detail="未认证")
        verify_token(credentials.credentials)
    cfg.set("auth_password_hash", _hash_pw(body.password))
    token = create_token()
    return {"ok": True, "access_token": token, "token_type": "bearer"}


@router.post("/disable")
def disable_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)):
    """Disable password protection. Requires auth only if a password is currently set."""
    cfg = _cfg()
    if cfg.get("auth_password_hash", ""):
        if credentials is None:
            raise HTTPException(status_code=401, detail="未认证")
        verify_token(credentials.credentials)
    cfg.set("auth_password_hash", "")
    cfg.set("auth_totp_secret", "")
    return {"ok": True}


@router.post("/login")
def login(body: LoginRequest):
    cfg = _cfg()
    stored = cfg.get("auth_password_hash", "")
    if not stored:
        raise HTTPException(status_code=403, detail="no_password_set")
    if not hmac.compare_digest(_hash_pw(body.password), stored):
        raise HTTPException(status_code=401, detail="密码错误")
    totp_secret = cfg.get("auth_totp_secret", "")
    if totp_secret:
        temp = secrets.token_hex(24)
        _pending_2fa[temp] = time.time() + 300  # 5 min expiry
        return {"requires_2fa": True, "temp_token": temp}
    token = create_token()
    return {"requires_2fa": False, "access_token": token, "token_type": "bearer"}


@router.post("/verify-totp")
def verify_totp_route(body: TotpVerifyRequest):
    expiry = _pending_2fa.get(body.temp_token)
    if not expiry or time.time() > expiry:
        raise HTTPException(status_code=401, detail="临时令牌无效或已过期，请重新登录")
    cfg = _cfg()
    secret = cfg.get("auth_totp_secret", "")
    if not secret:
        raise HTTPException(status_code=400, detail="2FA 未启用")
    if not verify_totp(secret, body.code):
        raise HTTPException(status_code=400, detail="验证码错误")
    _pending_2fa.pop(body.temp_token, None)
    token = create_token()
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
def logout():
    return {"ok": True}


@router.post("/change-password", dependencies=[Depends(require_auth)])
def change_password(body: ChangePasswordRequest):
    cfg = _cfg()
    stored = cfg.get("auth_password_hash", "")
    if stored and not hmac.compare_digest(_hash_pw(body.current_password), stored):
        raise HTTPException(status_code=400, detail="当前密码错误")
    if not body.new_password or len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少需要 6 位")
    cfg.set("auth_password_hash", _hash_pw(body.new_password))
    return {"ok": True}


@router.get("/2fa/setup", dependencies=[Depends(require_auth)])
def setup_2fa():
    secret = generate_totp_secret()
    return {"secret": secret, "uri": totp_uri(secret)}


@router.post("/2fa/enable", dependencies=[Depends(require_auth)])
def enable_2fa(body: EnableTotpRequest):
    if not body.secret or len(body.secret) < 16:
        raise HTTPException(status_code=400, detail="无效的密钥")
    if not verify_totp(body.secret, body.code):
        raise HTTPException(status_code=400, detail="验证码错误，请重试")
    _cfg().set("auth_totp_secret", body.secret)
    return {"ok": True}


@router.post("/2fa/disable", dependencies=[Depends(require_auth)])
def disable_2fa():
    _cfg().set("auth_totp_secret", "")
    return {"ok": True}
