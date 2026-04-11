import json
import os
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    ACCOUNT_TYPE_MICROSOFT_OAUTH,
    AutoDetectRowParser,
    DuplicateMicrosoftMailboxRule,
    MicrosoftMailImportRecord,
    MailApiUrlFormatRule,
    MicrosoftMailImportRuleEngine,
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
    @staticmethod
    def _generate_alias_email(email: str) -> str:
        local, domain = str(email or "").split("@", 1)
        base_local = local.split("+", 1)[0]
        suffix = "".join(random.choices(string.ascii_lowercase, k=6))
        return f"{base_local}+{suffix}@{domain}"

    @staticmethod
    def _expand_records_with_aliases(
        records: list[MicrosoftMailImportRecord],
        *,
        enabled: bool,
        alias_count: int,
        include_original: bool,
    ) -> list[MicrosoftMailImportRecord]:
        if not enabled:
            return records

        expanded: list[MicrosoftMailImportRecord] = []
        target_count = max(1, min(int(alias_count or 1), 5))

        for record in records:
            emails: list[str] = []
            seen_emails: set[str] = set()
            if include_original:
                emails.append(record.email)
                seen_emails.add(record.email)

            aliases: list[str] = []
            max_attempts = max(20, target_count * 20)
            attempts = 0
            while len(aliases) < target_count and attempts < max_attempts:
                candidate = MicrosoftMailImportStrategy._generate_alias_email(record.email)
                attempts += 1
                if candidate in seen_emails:
                    continue
                seen_emails.add(candidate)
                aliases.append(candidate)

            emails.extend(aliases)
            if not emails:
                emails.append(record.email)

            for email in emails:
                expanded.append(
                    MicrosoftMailImportRecord(
                        line_number=record.line_number,
                        email=email,
                        password=record.password,
                        client_id=record.client_id,
                        refresh_token=record.refresh_token,
                        account_type=record.account_type,
                        mailapi_url=record.mailapi_url,
                    )
                )
        return expanded

    @staticmethod
    def _resolve_oauth_check_workers(total_records: int) -> int:
        default_workers = 8
        raw_value = str(os.getenv("MAIL_IMPORT_OAUTH_WORKERS", default_workers)).strip()
        try:
            configured = int(raw_value)
        except (TypeError, ValueError):
            configured = default_workers
        configured = max(1, min(configured, 32))
        return max(1, min(configured, max(total_records, 1)))

    @staticmethod
    def _evaluate_availability(record, mailbox: OutlookMailbox) -> dict[str, object]:
        if getattr(record, "account_type", ACCOUNT_TYPE_MICROSOFT_OAUTH) != ACCOUNT_TYPE_MICROSOFT_OAUTH:
            return {"ok": True, "message": "ok"}
        try:
            result = mailbox.probe_oauth_availability(
                email=record.email,
                client_id=record.client_id,
                refresh_token=record.refresh_token,
            )
        except Exception as exc:
            return {
                "ok": False,
                "message": f"行 {record.line_number}: 微软邮箱可用性检测异常: {exc}",
                "reason": "oauth_probe_exception",
            }

        if result.get("ok"):
            return {"ok": True, "message": "ok"}
        return {
            "ok": False,
            "message": f"行 {record.line_number}: {result.get('message') or '微软邮箱可用性检测未通过'}",
            "reason": result.get("reason", "oauth_token_failed"),
        }

    @property
    def descriptor(self) -> MailImportProviderDescriptor:
        return MailImportProviderDescriptor(
            type="microsoft",
            label="微软邮箱（Outlook / Hotmail，本地导入）",
            description="导入微软邮箱本地账号池，运行时从数据库取账号并通过 Graph / IMAP 策略轮询邮件（默认 Graph）。",
            helper_text="支持两种格式并自动识别：1) 邮箱----密码----client_id----refresh_token（微软 OAuth）；2) 邮箱----mailapi_url（MailAPI URL 轮询取码）。",
            content_placeholder=(
                "example@outlook.com----password----client_id----refresh_token\n"
                "example@hotmail.com----password----client_id----refresh_token\n"
                "example@hotmail.com----https://mailapi.icu/key?type=html&orderNo=xxx"
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
                has_oauth=bool(
                    str(getattr(account, "account_type", ACCOUNT_TYPE_MICROSOFT_OAUTH) or ACCOUNT_TYPE_MICROSOFT_OAUTH)
                    == ACCOUNT_TYPE_MICROSOFT_OAUTH
                    and account.client_id
                    and account.refresh_token
                ),
                account_type=str(
                    getattr(account, "account_type", ACCOUNT_TYPE_MICROSOFT_OAUTH)
                    or ACCOUNT_TYPE_MICROSOFT_OAUTH
                ),
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
        valid_records = []

        with Session(engine) as session:
            existing_emails = {
                str(email or "").strip()
                for email in session.exec(select(OutlookAccountModel.email)).all()
            }

        row_parser = AutoDetectRowParser()
        rule_engine = MicrosoftMailImportRuleEngine(
            rules=[
                DuplicateMicrosoftMailboxRule(),
                MailApiUrlFormatRule(),
            ]
        )
        batch_seen_emails: set[str] = set()
        for line_number, line in actionable_lines:
            try:
                record = row_parser.parse(line_number, line)
            except ValueError as exc:
                failed += 1
                errors.append(str(exc))
                continue

            if record.email in batch_seen_emails:
                failed += 1
                errors.append(f"行 {line_number}: 导入内容存在重复邮箱: {record.email}")
                continue
            batch_seen_emails.add(record.email)

            duplicate_check = rule_engine.evaluate(
                record,
                {"existing_emails": existing_emails},
            )
            if not duplicate_check.get("ok"):
                failed += 1
                errors.append(str(duplicate_check.get("message") or f"行 {line_number}: 导入失败"))
                continue
            valid_records.append(record)

        alias_enabled = bool(request.alias_split_enabled)
        alias_count = int(request.alias_split_count or 5)
        alias_include_original = bool(request.alias_include_original)
        valid_records = self._expand_records_with_aliases(
            valid_records,
            enabled=alias_enabled,
            alias_count=alias_count,
            include_original=alias_include_original,
        )

        oauth_records = [
            record
            for record in valid_records
            if getattr(record, "account_type", ACCOUNT_TYPE_MICROSOFT_OAUTH)
            == ACCOUNT_TYPE_MICROSOFT_OAUTH
        ]
        oauth_check_results: dict[int, dict[str, object]] = {}
        if oauth_records:
            mailbox = OutlookMailbox()
            max_workers = self._resolve_oauth_check_workers(len(oauth_records))
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="oauth-import") as executor:
                future_map = {
                    executor.submit(self._evaluate_availability, record, mailbox): record
                    for record in oauth_records
                }
                for future in as_completed(future_map):
                    record = future_map[future]
                    try:
                        oauth_check_results[record.line_number] = future.result()
                    except Exception as exc:
                        oauth_check_results[record.line_number] = {
                            "ok": False,
                            "message": f"行 {record.line_number}: 微软邮箱可用性检测异常: {exc}",
                            "reason": "oauth_probe_exception",
                        }

        passed_records = []
        for record in valid_records:
            if getattr(record, "account_type", ACCOUNT_TYPE_MICROSOFT_OAUTH) != ACCOUNT_TYPE_MICROSOFT_OAUTH:
                passed_records.append(record)
                continue
            check_result = oauth_check_results.get(record.line_number) or {
                "ok": False,
                "message": f"行 {record.line_number}: 微软邮箱可用性检测未返回结果",
                "reason": "oauth_probe_missing_result",
            }
            if not check_result.get("ok"):
                failed += 1
                errors.append(str(check_result.get("message") or f"行 {record.line_number}: 导入失败"))
                continue
            passed_records.append(record)

        with Session(engine) as session:
            for record in passed_records:
                try:
                    account = OutlookAccountModel(
                        email=record.email,
                        password=record.password,
                        client_id=record.client_id,
                        refresh_token=record.refresh_token,
                        account_type=str(record.account_type or ACCOUNT_TYPE_MICROSOFT_OAUTH),
                        mailapi_url=str(record.mailapi_url or ""),
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
                        "account_type": str(account.account_type or ACCOUNT_TYPE_MICROSOFT_OAUTH),
                        "has_oauth": bool(
                            str(account.account_type or ACCOUNT_TYPE_MICROSOFT_OAUTH) == ACCOUNT_TYPE_MICROSOFT_OAUTH
                            and account.client_id
                            and account.refresh_token
                        ),
                        "enabled": account.enabled,
                    })
                    success += 1
                except Exception as exc:
                    session.rollback()
                    failed += 1
                    errors.append(f"行 {record.line_number}: 创建失败: {str(exc)}")

        snapshot = self.get_snapshot(
            MailImportSnapshotRequest(
                type="microsoft",
                preview_limit=request.preview_limit,
            )
        )
        return MailImportResponse(
            type="microsoft",
            summary=MailImportSummary(
                total=success + failed,
                success=success,
                failed=failed,
            ),
            snapshot=snapshot,
            errors=errors,
            meta={
                "accounts": accounts,
                "alias_split_enabled": alias_enabled,
                "alias_split_count": alias_count,
                "alias_include_original": alias_include_original,
            },
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
