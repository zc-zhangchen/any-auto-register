from dataclasses import dataclass
from typing import Any, Optional, Protocol
from urllib.parse import urlparse


ACCOUNT_TYPE_MICROSOFT_OAUTH = "microsoft_oauth"
ACCOUNT_TYPE_MAILAPI_URL = "mailapi_url"


@dataclass
class MicrosoftMailImportRecord:
    line_number: int
    email: str
    password: str = ""
    client_id: str = ""
    refresh_token: str = ""
    account_type: str = ACCOUNT_TYPE_MICROSOFT_OAUTH
    mailapi_url: str = ""


class MicrosoftMailImportRule(Protocol):
    def evaluate(
        self,
        record: MicrosoftMailImportRecord,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class MicrosoftImportRowParser(Protocol):
    def parse(self, line_number: int, line: str) -> MicrosoftMailImportRecord:
        ...


def _is_valid_email(email: str) -> bool:
    return "@" in str(email or "").strip()


def _is_valid_mailapi_url(url: str) -> bool:
    text = str(url or "").strip()
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class MicrosoftOAuthRowParser:
    def parse(self, line_number: int, line: str) -> MicrosoftMailImportRecord:
        parts = [part.strip() for part in str(line or "").split("----")]
        if len(parts) < 4:
            raise ValueError(
                f"行 {line_number}: 格式错误，微软 OAuth 导入需为 邮箱----密码----client_id----refresh_token"
            )

        email = parts[0]
        password = parts[1]
        client_id = parts[2]
        refresh_token = parts[3]

        if not _is_valid_email(email):
            raise ValueError(f"行 {line_number}: 无效的邮箱地址: {email}")
        if not password:
            raise ValueError(f"行 {line_number}: 缺少密码")
        if not client_id or not refresh_token:
            raise ValueError(
                f"行 {line_number}: 缺少 client_id 或 refresh_token，无法通过微软邮箱可用性检测"
            )

        return MicrosoftMailImportRecord(
            line_number=line_number,
            email=email,
            password=password,
            client_id=client_id,
            refresh_token=refresh_token,
            account_type=ACCOUNT_TYPE_MICROSOFT_OAUTH,
            mailapi_url="",
        )


class MailApiUrlRowParser:
    def parse(self, line_number: int, line: str) -> MicrosoftMailImportRecord:
        parts = [part.strip() for part in str(line or "").split("----")]
        if len(parts) < 2:
            raise ValueError(
                f"行 {line_number}: 格式错误，MailAPI URL 导入需为 邮箱----mailapi_url"
            )

        email = parts[0]
        mailapi_url = parts[1]

        if not _is_valid_email(email):
            raise ValueError(f"行 {line_number}: 无效的邮箱地址: {email}")
        if not _is_valid_mailapi_url(mailapi_url):
            raise ValueError(
                f"行 {line_number}: 无效的 mailapi_url（需为 http/https）：{mailapi_url}"
            )

        return MicrosoftMailImportRecord(
            line_number=line_number,
            email=email,
            password="",
            client_id="",
            refresh_token="",
            account_type=ACCOUNT_TYPE_MAILAPI_URL,
            mailapi_url=mailapi_url,
        )


class AutoDetectRowParser:
    def __init__(
        self,
        oauth_parser: Optional[MicrosoftImportRowParser] = None,
        mailapi_parser: Optional[MicrosoftImportRowParser] = None,
    ):
        self._oauth_parser = oauth_parser or MicrosoftOAuthRowParser()
        self._mailapi_parser = mailapi_parser or MailApiUrlRowParser()

    def parse(self, line_number: int, line: str) -> MicrosoftMailImportRecord:
        parts = [part.strip() for part in str(line or "").split("----")]
        if len(parts) == 2:
            return self._mailapi_parser.parse(line_number, line)
        if len(parts) >= 4:
            return self._oauth_parser.parse(line_number, line)
        raise ValueError(
            f"行 {line_number}: 格式错误，仅支持 邮箱----mailapi_url 或 邮箱----密码----client_id----refresh_token"
        )


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


class MailApiUrlFormatRule:
    def evaluate(
        self,
        record: MicrosoftMailImportRecord,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if record.account_type != ACCOUNT_TYPE_MAILAPI_URL:
            return {"ok": True, "message": "ok"}
        if not _is_valid_mailapi_url(record.mailapi_url):
            return {
                "ok": False,
                "message": f"行 {record.line_number}: 无效的 mailapi_url（需为 http/https）：{record.mailapi_url}",
            }
        return {"ok": True, "message": "ok"}


class MicrosoftMailboxAvailabilityRule:
    def __init__(self, mailbox: Any):
        self._mailbox = mailbox

    def evaluate(
        self,
        record: MicrosoftMailImportRecord,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if record.account_type != ACCOUNT_TYPE_MICROSOFT_OAUTH:
            return {"ok": True, "message": "ok"}
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
    """兼容旧调用：仅按微软 OAuth 四段格式解析。"""
    parts = [part.strip() for part in str(line or "").split("----")]
    if len(parts) >= 2 and len(parts) < 4:
        raise ValueError(
            f"行 {line_number}: 缺少 client_id 或 refresh_token，无法通过微软邮箱可用性检测"
        )
    return MicrosoftOAuthRowParser().parse(line_number, line)


def parse_microsoft_import_line(line_number: int, line: str) -> MicrosoftMailImportRecord:
    """按行格式自动识别：2 段=MailAPI URL，4 段=微软 OAuth。"""
    return AutoDetectRowParser().parse(line_number, line)
