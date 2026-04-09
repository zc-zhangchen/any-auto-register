from __future__ import annotations

from sqlmodel import Session, select

from core.db import OutlookAccountLeaseModel, OutlookAccountModel, _utcnow, engine

from .schemas import (
    MailRecoveryPoolItem,
    MailRecoveryPoolMailboxType,
    MailRecoveryPoolRequest,
    MailRecoveryPoolResponse,
    MailRecoveryPoolSummary,
)


def resolve_mailbox_type(email: str) -> MailRecoveryPoolMailboxType:
    domain = str(email or "").strip().lower().split("@")[-1]
    if "hotmail" in domain:
        return "hotmail"
    if "outlook" in domain:
        return "outlook"
    return "other"


def restore_microsoft_recovery_item(item_id: int) -> MailRecoveryPoolItem:
    with Session(engine) as session:
        row = session.get(OutlookAccountLeaseModel, item_id)
        if row is None:
            raise RuntimeError("未找到要恢复的微软邮箱记录")
        if str(row.status or "") != "recoverable":
            raise RuntimeError("当前仅支持恢复“可恢复”状态的微软邮箱")

        existing = session.exec(
            select(OutlookAccountModel).where(OutlookAccountModel.email == row.email)
        ).first()
        now = _utcnow()
        if existing is not None:
            existing.password = row.password
            existing.client_id = row.client_id
            existing.refresh_token = row.refresh_token
            existing.enabled = True
            existing.updated_at = now
            session.add(existing)
        else:
            session.add(
                OutlookAccountModel(
                    email=row.email,
                    password=row.password,
                    client_id=row.client_id,
                    refresh_token=row.refresh_token,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )

        restored_item = MailRecoveryPoolItem(
            id=int(row.id or 0),
            email=str(row.email or ""),
            mailbox_type=resolve_mailbox_type(row.email),
            status=str(row.status or ""),
            has_oauth=bool(row.client_id and row.refresh_token),
            source_account_id=row.source_account_id,
            task_attempt_id=str(row.task_attempt_id or ""),
            last_error=str(row.last_error or ""),
            leased_at=row.leased_at,
            last_failed_at=row.last_failed_at,
            updated_at=row.updated_at,
        )
        session.delete(row)
        session.commit()
        return restored_item


def get_microsoft_recovery_pool(
    request: MailRecoveryPoolRequest,
) -> MailRecoveryPoolResponse:
    with Session(engine) as session:
        rows = session.exec(
            select(OutlookAccountLeaseModel).order_by(
                OutlookAccountLeaseModel.updated_at.desc(),
                OutlookAccountLeaseModel.id.desc(),
            )
        ).all()

    normalized_search = str(request.search or "").strip().lower()

    summary = MailRecoveryPoolSummary(
        total=len(rows),
        leased=sum(1 for row in rows if str(row.status or "") == "leased"),
        recoverable=sum(1 for row in rows if str(row.status or "") == "recoverable"),
        hotmail=sum(1 for row in rows if resolve_mailbox_type(row.email) == "hotmail"),
        outlook=sum(1 for row in rows if resolve_mailbox_type(row.email) == "outlook"),
        other=sum(1 for row in rows if resolve_mailbox_type(row.email) == "other"),
    )

    def matches(row: OutlookAccountLeaseModel) -> bool:
        mailbox_type = resolve_mailbox_type(row.email)
        if request.mailbox_type != "all" and mailbox_type != request.mailbox_type:
            return False
        if request.status != "all" and str(row.status or "") != request.status:
            return False
        if not normalized_search:
            return True

        haystacks = (
            str(row.email or "").lower(),
            str(row.last_error or "").lower(),
            str(row.task_attempt_id or "").lower(),
        )
        return any(normalized_search in value for value in haystacks)

    filtered_rows = [row for row in rows if matches(row)]
    limited_rows = filtered_rows[: request.limit]

    items = [
        MailRecoveryPoolItem(
            id=int(row.id or 0),
            email=str(row.email or ""),
            mailbox_type=resolve_mailbox_type(row.email),
            status=str(row.status or ""),
            has_oauth=bool(row.client_id and row.refresh_token),
            source_account_id=row.source_account_id,
            task_attempt_id=str(row.task_attempt_id or ""),
            last_error=str(row.last_error or ""),
            leased_at=row.leased_at,
            last_failed_at=row.last_failed_at,
            updated_at=row.updated_at,
        )
        for row in limited_rows
    ]

    return MailRecoveryPoolResponse(
        mailbox_type=request.mailbox_type,
        status=request.status,
        search=str(request.search or ""),
        count=len(filtered_rows),
        items=items,
        truncated=len(filtered_rows) > request.limit,
        summary=summary,
    )
