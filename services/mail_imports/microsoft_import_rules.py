from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class MicrosoftMailImportRecord:
    line_number: int
    email: str
    password: str
    client_id: str
    refresh_token: str


class MicrosoftMailImportRule(Protocol):
    def evaluate(
        self,
        record: MicrosoftMailImportRecord,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class MicrosoftMailImportRuleEngine:
    def __init__(self, rules: list[MicrosoftMailImportRule]):
        self._rules = list(rules)

    def evaluate(
        self,
        record: MicrosoftMailImportRecord,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        for rule in self._rules:
            result = rule.evaluate(record, context)
            if not result.get("ok"):
                return result
        return {"ok": True, "message": "ok"}


class DuplicateMicrosoftMailboxRule:
    def evaluate(
        self,
        record: MicrosoftMailImportRecord,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        existing_emails = context.get("existing_emails") or set()
        if record.email in existing_emails:
            return {"ok": False, "message": f"行 {record.line_number}: 邮箱已存在: {record.email}"}
        return {"ok": True, "message": "ok"}


class MicrosoftMailboxAvailabilityRule:
    def __init__(self, mailbox: Any):
        self._mailbox = mailbox

    def evaluate(
        self,
        record: MicrosoftMailImportRecord,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        result = self._mailbox.probe_oauth_availability(
            email=record.email,
            client_id=record.client_id,
            refresh_token=record.refresh_token,
        )
        if result.get("ok"):
            return {"ok": True, "message": "ok"}
        return {
            "ok": False,
            "message": f"行 {record.line_number}: {result.get('message') or '微软邮箱可用性检测未通过'}",
            "reason": result.get("reason", "oauth_token_failed"),
        }


def parse_microsoft_import_record(line_number: int, line: str) -> MicrosoftMailImportRecord:
    parts = [part.strip() for part in str(line or "").split("----")]
    if len(parts) < 2:
        raise ValueError(f"行 {line_number}: 格式错误，至少需要邮箱和密码")

    email = parts[0]
    password = parts[1]
    client_id = parts[2] if len(parts) >= 3 else ""
    refresh_token = parts[3] if len(parts) >= 4 else ""

    if "@" not in email:
        raise ValueError(f"行 {line_number}: 无效的邮箱地址: {email}")
    if not password:
        raise ValueError(f"行 {line_number}: 缺少密码")
    if not client_id or not refresh_token:
        raise ValueError(f"行 {line_number}: 缺少 client_id 或 refresh_token，无法通过微软邮箱可用性检测")

    return MicrosoftMailImportRecord(
        line_number=line_number,
        email=email,
        password=password,
        client_id=client_id,
        refresh_token=refresh_token,
    )
