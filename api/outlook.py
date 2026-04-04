from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import Session, select

from core.db import engine, OutlookAccountModel

router = APIRouter(prefix="/outlook", tags=["outlook"])


def _utcnow():
    return datetime.now(timezone.utc)


class OutlookBatchImportRequest(BaseModel):
    data: str
    enabled: bool = True


class OutlookBatchImportResponse(BaseModel):
    total: int
    success: int
    failed: int
    accounts: List[Dict[str, Any]]
    errors: List[str]


@router.get("/count")
def get_outlook_count():
    """返回 Outlook 邮箱总数"""
    with Session(engine) as session:
        from sqlmodel import func
        count = session.exec(select(func.count()).select_from(OutlookAccountModel)).one()
        return {"count": count}


@router.post("/batch-import", response_model=OutlookBatchImportResponse)
def batch_import_outlook(request: OutlookBatchImportRequest):
    """
    批量导入 Outlook 邮箱账户

    支持两种格式（每行一个账户，字段用 ---- 分隔）：
    - 邮箱----密码
    - 邮箱----密码----client_id----refresh_token
    """
    lines = (request.data or "").splitlines()
    total = len(lines)
    success = 0
    failed = 0
    accounts: List[Dict[str, Any]] = []
    errors: List[str] = []

    with Session(engine) as session:
        for idx, raw_line in enumerate(lines):
            line = str(raw_line or "").strip()
            if not line or line.startswith("#"):
                continue

            parts = [part.strip() for part in line.split("----")]
            if len(parts) < 2:
                failed += 1
                errors.append(f"行 {idx + 1}: 格式错误，至少需要邮箱和密码")
                continue

            email = parts[0]
            password = parts[1]
            if "@" not in email:
                failed += 1
                errors.append(f"行 {idx + 1}: 无效的邮箱地址: {email}")
                continue

            existing = session.exec(
                select(OutlookAccountModel).where(OutlookAccountModel.email == email)
            ).first()
            if existing:
                failed += 1
                errors.append(f"行 {idx + 1}: 邮箱已存在: {email}")
                continue

            client_id = parts[2] if len(parts) >= 3 else ""
            refresh_token = parts[3] if len(parts) >= 4 else ""

            try:
                account = OutlookAccountModel(
                    email=email,
                    password=password,
                    client_id=client_id,
                    refresh_token=refresh_token,
                    enabled=bool(request.enabled),
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                session.add(account)
                session.commit()
                session.refresh(account)

                accounts.append(
                    {
                        "id": account.id,
                        "email": account.email,
                        "has_oauth": bool(account.client_id and account.refresh_token),
                        "enabled": account.enabled,
                    }
                )
                success += 1
            except Exception as e:
                session.rollback()
                failed += 1
                errors.append(f"行 {idx + 1}: 创建失败: {str(e)}")

    return OutlookBatchImportResponse(
        total=total,
        success=success,
        failed=failed,
        accounts=accounts,
        errors=errors,
    )

