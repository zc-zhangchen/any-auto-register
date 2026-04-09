import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from core.base_mailbox import OutlookMailbox
from core.applemail_pool import (
    load_applemail_pool_records,
    load_applemail_pool_snapshot,
    save_applemail_pool_json,
)
from core.config_store import config_store
from core.db import OutlookAccountModel, engine

from .base import BaseMailImportStrategy
from .microsoft_import_rules import (
    DuplicateMicrosoftMailboxRule,
    MicrosoftMailboxAvailabilityRule,
    MicrosoftMailImportRuleEngine,
    parse_microsoft_import_record,
)
from .schemas import (
    MailImportBatchDeleteRequest,
    MailImportDeleteItem,
    MailImportExecuteRequest,
    MailImportDeleteRequest,
    MailImportProviderDescriptor,
    MailImportResponse,
    MailImportSnapshot,
    MailImportSnapshotItem,
    MailImportSnapshotRequest,
    MailImportSummary,
)


def _utcnow():
    return datetime.now(timezone.utc)


class AppleMailImportStrategy(BaseMailImportStrategy):
    def _delete_records(
        self,
        records: list[dict[str, str]],
        items: list[MailImportDeleteItem],
    ) -> tuple[list[dict[str, str]], list[str], list[str]]:
        pending = [
            (
                str(item.email or "").strip().lower(),
                str(item.mailbox or "").strip().lower(),
            )
            for item in items
            if str(item.email or "").strip()
        ]
        deleted: list[str] = []
        errors: list[str] = []
        remaining: list[dict[str, str]] = []

        for record in records:
            record_email = str(record.get("email") or "").strip().lower()
            record_mailbox = str(record.get("mailbox") or "INBOX").strip().lower()
            match_index = next((
                idx for idx, (email, mailbox) in enumerate(pending)
                if email == record_email and (not mailbox or mailbox == record_mailbox)
            ), -1)
            if match_index >= 0:
                pending_email, _ = pending.pop(match_index)
                deleted.append(pending_email)
                continue
            remaining.append(record)

        for email, _ in pending:
            errors.append(f"未找到要删除的小苹果邮箱: {email}")

        return remaining, deleted, errors

    @property
    def descriptor(self) -> MailImportProviderDescriptor:
        return MailImportProviderDescriptor(
            type="applemail",
            label="AppleMail / 小苹果",
            description="导入本地邮箱池文件，运行时按文件轮询邮箱并通过 AppleMail API 拉取邮件。",
            helper_text=(
                "支持数组/对象 JSON，也支持每行一条的 "
                "`email----password----client_id----refresh_token` 文本。"
            ),
            content_placeholder=(
                '[\n  {\n    "email": "demo@example.com",\n    "clientId": "xxxx",\n'
                '    "refreshToken": "xxxx",\n    "folder": "INBOX"\n  }\n]\n\n'
                "或粘贴 TXT:\ndemo@example.com----password----client_id----refresh_token"
            ),
            supports_filename=True,
            filename_label="邮箱池文件名",
            filename_placeholder="可选文件名，例如 applemail_hotmail.json；留空自动生成",
            preview_empty_text="当前还没有可预览的 AppleMail 邮箱池内容。",
        )

    def get_snapshot(self, request: MailImportSnapshotRequest) -> MailImportSnapshot:
        pool_dir = str(
            request.pool_dir or config_store.get("applemail_pool_dir", "mail")
        ).strip() or "mail"
        pool_file = str(
            request.pool_file or config_store.get("applemail_pool_file", "")
        ).strip()
        try:
            snapshot = load_applemail_pool_snapshot(
                pool_file=pool_file,
                pool_dir=pool_dir,
                preview_limit=request.preview_limit,
            )
        except Exception:
            snapshot = {
                "filename": pool_file,
                "path": "",
                "count": 0,
                "items": [],
                "truncated": False,
            }

        items = [
            MailImportSnapshotItem(
                index=int(item.get("index") or 0),
                email=str(item.get("email") or ""),
                mailbox=str(item.get("mailbox") or "INBOX"),
            )
            for item in snapshot.get("items", [])
        ]

        return MailImportSnapshot(
            type="applemail",
            label=self.descriptor.label,
            count=int(snapshot.get("count") or 0),
            items=items,
            truncated=bool(snapshot.get("truncated")),
            filename=str(snapshot.get("filename") or ""),
            path=str(snapshot.get("path") or ""),
            pool_dir=pool_dir,
        )

    def execute(self, request: MailImportExecuteRequest) -> MailImportResponse:
        pool_dir = str(
            request.pool_dir or config_store.get("applemail_pool_dir", "mail")
        ).strip() or "mail"
        result = save_applemail_pool_json(
            request.content,
            pool_dir=pool_dir,
            filename=request.filename,
        )

        if request.bind_to_config:
            config_store.set_many(
                {
                    "applemail_pool_dir": pool_dir,
                    "applemail_pool_file": result["filename"],
                }
            )

        snapshot = self.get_snapshot(
            MailImportSnapshotRequest(
                type="applemail",
                pool_dir=pool_dir,
                pool_file=str(result["filename"]),
                preview_limit=request.preview_limit,
            )
        )
        return MailImportResponse(
            type="applemail",
            summary=MailImportSummary(
                total=int(result["count"]),
                success=int(result["count"]),
                failed=0,
            ),
            snapshot=snapshot,
            meta={
                "bound_to_config": request.bind_to_config,
                "path": str(result["path"]),
            },
        )

    def delete(self, request: MailImportDeleteRequest) -> MailImportResponse:
        pool_dir = str(
            request.pool_dir or config_store.get("applemail_pool_dir", "mail")
        ).strip() or "mail"
        pool_file = str(
            request.pool_file or config_store.get("applemail_pool_file", "")
        ).strip()
        path, records = load_applemail_pool_records(pool_file=pool_file, pool_dir=pool_dir)

        target_email = str(request.email or "").strip().lower()
        target_mailbox = str(request.mailbox or "").strip().lower()
        removed = None
        remaining: list[dict[str, str]] = []

        for record in records:
            record_email = str(record.get("email") or "").strip().lower()
            record_mailbox = str(record.get("mailbox") or "INBOX").strip().lower()
            is_match = record_email == target_email and (
                not target_mailbox or record_mailbox == target_mailbox
            )
            if removed is None and is_match:
                removed = record
                continue
            remaining.append(record)

        if removed is None:
            raise RuntimeError(f"未找到要删除的小苹果邮箱: {request.email}")

        path.write_text(
            json.dumps(remaining, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        snapshot = self.get_snapshot(
            MailImportSnapshotRequest(
                type="applemail",
                pool_dir=pool_dir,
                pool_file=path.name,
                preview_limit=request.preview_limit,
            )
        )
        return MailImportResponse(
            type="applemail",
            summary=MailImportSummary(total=1, success=1, failed=0),
            snapshot=snapshot,
            meta={
                "deleted_email": request.email,
                "deleted_mailbox": request.mailbox,
                "path": str(path),
            },
        )

    def batch_delete(self, request: MailImportBatchDeleteRequest) -> MailImportResponse:
        pool_dir = str(
            request.pool_dir or config_store.get("applemail_pool_dir", "mail")
        ).strip() or "mail"
        pool_file = str(
            request.pool_file or config_store.get("applemail_pool_file", "")
        ).strip()
        path, records = load_applemail_pool_records(pool_file=pool_file, pool_dir=pool_dir)

        remaining, deleted, errors = self._delete_records(records, request.items)
        path.write_text(
            json.dumps(remaining, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        snapshot = self.get_snapshot(
            MailImportSnapshotRequest(
                type="applemail",
                pool_dir=pool_dir,
                pool_file=path.name,
                preview_limit=request.preview_limit,
            )
        )
        return MailImportResponse(
            type="applemail",
            summary=MailImportSummary(
                total=len(request.items),
                success=len(deleted),
                failed=len(errors),
            ),
            snapshot=snapshot,
            errors=errors,
            meta={
                "deleted_emails": deleted,
                "path": str(path),
            },
        )


class MicrosoftMailImportStrategy(BaseMailImportStrategy):
    @property
    def descriptor(self) -> MailImportProviderDescriptor:
        return MailImportProviderDescriptor(
            type="microsoft",
            label="微软邮箱（Outlook / Hotmail，本地导入）",
            description="导入微软邮箱本地账号池，运行时从数据库取账号并通过 Graph / IMAP 策略轮询邮件（默认 Graph）。",
            helper_text="每行格式：邮箱----密码----client_id----refresh_token；导入时会执行微软邮箱可用性检测，缺少 OAuth 凭据或命中 service abuse mode 的账号不会入库。",
            content_placeholder=(
                "example@outlook.com----password----client_id----refresh_token\n"
                "example@hotmail.com----password----client_id----refresh_token"
            ),
            preview_empty_text="当前还没有已导入的微软邮箱本地账号。",
        )

    def get_snapshot(self, request: MailImportSnapshotRequest) -> MailImportSnapshot:
        with Session(engine) as session:
            accounts = session.exec(
                select(OutlookAccountModel).order_by(OutlookAccountModel.id)
            ).all()

        limit = max(int(request.preview_limit or 0), 0)
        preview = accounts[:limit] if limit else []
        items = [
            MailImportSnapshotItem(
                index=idx,
                email=account.email,
                enabled=bool(account.enabled),
                has_oauth=bool(account.client_id and account.refresh_token),
            )
            for idx, account in enumerate(preview, start=1)
        ]

        return MailImportSnapshot(
            type="microsoft",
            label=self.descriptor.label,
            count=len(accounts),
            items=items,
            truncated=len(accounts) > limit if limit > 0 else len(accounts) > 0,
        )

    def execute(self, request: MailImportExecuteRequest) -> MailImportResponse:
        lines = (request.content or "").splitlines()
        actionable_lines = [
            (idx, str(raw_line or "").strip())
            for idx, raw_line in enumerate(lines, start=1)
            if str(raw_line or "").strip() and not str(raw_line or "").strip().startswith("#")
        ]
        success = 0
        failed = 0
        errors: list[str] = []
        accounts: list[dict[str, object]] = []
        mailbox = OutlookMailbox()

        with Session(engine) as session:
            existing_emails = {
                str(email or "").strip()
                for email in session.exec(select(OutlookAccountModel.email)).all()
            }
            engine_ctx = {"existing_emails": existing_emails}
            rule_engine = MicrosoftMailImportRuleEngine([
                DuplicateMicrosoftMailboxRule(),
                MicrosoftMailboxAvailabilityRule(mailbox),
            ])

            for line_number, line in actionable_lines:
                try:
                    record = parse_microsoft_import_record(line_number, line)
                except ValueError as exc:
                    failed += 1
                    errors.append(str(exc))
                    continue

                result = rule_engine.evaluate(record, engine_ctx)
                if not result.get("ok"):
                    failed += 1
                    errors.append(str(result.get("message") or f"行 {line_number}: 导入失败"))
                    continue

                try:
                    account = OutlookAccountModel(
                        email=record.email,
                        password=record.password,
                        client_id=record.client_id,
                        refresh_token=record.refresh_token,
                        enabled=bool(request.enabled),
                        created_at=_utcnow(),
                        updated_at=_utcnow(),
                    )
                    session.add(account)
                    session.commit()
                    session.refresh(account)
                    existing_emails.add(record.email)
                    accounts.append({
                        "id": account.id,
                        "email": account.email,
                        "has_oauth": True,
                        "enabled": account.enabled,
                    })
                    success += 1
                except Exception as exc:
                    session.rollback()
                    failed += 1
                    errors.append(f"行 {line_number}: 创建失败: {str(exc)}")

        snapshot = self.get_snapshot(
            MailImportSnapshotRequest(
                type="microsoft",
                preview_limit=request.preview_limit,
            )
        )
        return MailImportResponse(
            type="microsoft",
            summary=MailImportSummary(
                total=len(actionable_lines),
                success=success,
                failed=failed,
            ),
            snapshot=snapshot,
            errors=errors,
            meta={"accounts": accounts},
        )

    def delete(self, request: MailImportDeleteRequest) -> MailImportResponse:
        email = str(request.email or "").strip()
        if not email:
            raise RuntimeError("缺少要删除的邮箱地址")

        with Session(engine) as session:
            account = session.exec(
                select(OutlookAccountModel).where(OutlookAccountModel.email == email)
            ).first()
            if not account:
                raise RuntimeError(f"未找到要删除的微软邮箱: {email}")

            session.delete(account)
            session.commit()

        snapshot = self.get_snapshot(
            MailImportSnapshotRequest(
                type="microsoft",
                preview_limit=request.preview_limit,
            )
        )
        return MailImportResponse(
            type="microsoft",
            summary=MailImportSummary(total=1, success=1, failed=0),
            snapshot=snapshot,
            meta={"deleted_email": email},
        )

    def batch_delete(self, request: MailImportBatchDeleteRequest) -> MailImportResponse:
        targets = [
            str(item.email or "").strip()
            for item in request.items
            if str(item.email or "").strip()
        ]
        deleted: list[str] = []
        errors: list[str] = []

        with Session(engine) as session:
            for email in targets:
                account = session.exec(
                    select(OutlookAccountModel).where(OutlookAccountModel.email == email)
                ).first()
                if not account:
                    errors.append(f"未找到要删除的微软邮箱: {email}")
                    continue
                session.delete(account)
                deleted.append(email)
            session.commit()

        snapshot = self.get_snapshot(
            MailImportSnapshotRequest(
                type="microsoft",
                preview_limit=request.preview_limit,
            )
        )
        return MailImportResponse(
            type="microsoft",
            summary=MailImportSummary(
                total=len(targets),
                success=len(deleted),
                failed=len(errors),
            ),
            snapshot=snapshot,
            errors=errors,
            meta={"deleted_emails": deleted},
        )
