from fastapi import APIRouter

from core.tmailor_mailbox import (
    add_to_blocked_pool,
    clear_blocked_pool,
    get_blocked_pool,
    remove_from_blocked_pool,
)

router = APIRouter(prefix="/tmailor", tags=["tmailor"])


@router.get("/blocked-pool")
def list_blocked_pool():
    return {"items": get_blocked_pool()}


@router.post("/blocked-pool")
def add_blocked(email: str, reason: str = "add_phone", extra: dict = None):
    add_to_blocked_pool(email, reason=reason, extra=extra)
    return {"message": "已加入封禁池", "email": email}


@router.delete("/blocked-pool/{email}")
def delete_blocked(email: str):
    removed = remove_from_blocked_pool(email)
    if removed:
        return {"message": "已从封禁池移除", "email": email}
    return {"message": "未找到该邮箱", "email": email}


@router.delete("/blocked-pool")
def clear_blocked():
    clear_blocked_pool()
    return {"message": "封禁池已清空"}
