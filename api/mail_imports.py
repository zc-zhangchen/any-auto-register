from fastapi import APIRouter, HTTPException, Query

from services.mail_imports import (
    MailImportBatchDeleteRequest,
    MailImportDeleteRequest,
    MailImportExecuteRequest,
    MailImportSnapshotRequest,
    mail_import_registry,
)
from services.mail_imports.recovery_pool import (
    get_microsoft_recovery_pool,
    restore_microsoft_recovery_item,
)
from services.mail_imports.schemas import (
    MailRecoveryPoolRequest,
    MailRecoveryPoolRestoreRequest,
)

router = APIRouter(prefix="/mail-imports", tags=["mail-imports"])


@router.get("/providers")
def list_mail_import_providers():
    return {"items": mail_import_registry.descriptors()}


@router.get("/snapshot")
def get_mail_import_snapshot(
    provider_type: str = Query(alias="type"),
    pool_dir: str = "",
    pool_file: str = "",
    preview_limit: int = 100,
):
    try:
        strategy = mail_import_registry.get(provider_type)
        request = MailImportSnapshotRequest(
            type=strategy.descriptor.type,
            pool_dir=pool_dir,
            pool_file=pool_file,
            preview_limit=preview_limit,
        )
        return strategy.get_snapshot(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/recovery-pool")
def get_recovery_pool_snapshot(
    mailbox_type: str = Query(default="all"),
    status: str = Query(default="all"),
    search: str = "",
    limit: int = 100,
):
    try:
        request = MailRecoveryPoolRequest(
            mailbox_type=mailbox_type,
            status=status,
            search=search,
            limit=limit,
        )
        return get_microsoft_recovery_pool(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recovery-pool/restore")
def restore_recovery_pool_item(body: MailRecoveryPoolRestoreRequest):
    try:
        item = restore_microsoft_recovery_item(body.id)
        return {"ok": True, "item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
def execute_mail_import(body: MailImportExecuteRequest):
    try:
        strategy = mail_import_registry.get(body.type)
        return strategy.execute(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/delete")
def delete_mail_import_item(body: MailImportDeleteRequest):
    try:
        strategy = mail_import_registry.get(body.type)
        return strategy.delete(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batch-delete")
def batch_delete_mail_import_items(body: MailImportBatchDeleteRequest):
    try:
        strategy = mail_import_registry.get(body.type)
        return strategy.batch_delete(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
