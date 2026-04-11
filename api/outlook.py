from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
from services.mail_imports import MailImportExecuteRequest, mail_import_registry
from core.db import OutlookAccountModel, engine

router = APIRouter(prefix="/outlook", tags=["微软邮箱（Outlook / Hotmail）"])


class OutlookBatchImportRequest(BaseModel):
    data: str
    enabled: bool = True


class OutlookBatchImportResponse(BaseModel):
    total: int
    success: int
    failed: int
    accounts: List[Dict[str, Any]]
    errors: List[str]


@router.post("/batch-import", response_model=OutlookBatchImportResponse)
def batch_import_outlook(request: OutlookBatchImportRequest):
    """
    批量导入微软邮箱（Outlook / Hotmail）账户

    支持两种格式（每行一个账户，字段用 ---- 分隔）：
    - 邮箱----密码----client_id----refresh_token（微软 OAuth）
    - 邮箱----mailapi_url（MailAPI URL 轮询取码）

    运行时默认优先使用 Graph 后端读取邮件；MailAPI URL 账号会走 URL 轮询取码。
    """
    try:
        strategy = mail_import_registry.get("microsoft")
        result = strategy.execute(
            MailImportExecuteRequest(
                type="microsoft",
                content=request.data,
                enabled=request.enabled,
            )
        )
        return OutlookBatchImportResponse(
            total=result.summary.total,
            success=result.summary.success,
            failed=result.summary.failed,
            accounts=list(result.meta.get("accounts") or []),
            errors=result.errors,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

