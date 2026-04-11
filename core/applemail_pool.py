from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


_POOL_CURSOR_LOCK = threading.Lock()
_POOL_CURSORS: dict[str, int] = {}


def _project_root() -> Path:
    return Path.cwd()


def _normalize_pool_dir(pool_dir: str | None = None) -> Path:
    raw = str(pool_dir or "mail").strip() or "mail"
    path = Path(raw)
    if path.is_absolute():
        return path
    return _project_root() / path


def _normalize_filename(filename: str | None = None) -> str:
    raw = Path(str(filename or "").strip() or "").name
    if not raw:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"applemail_{timestamp}.json"

    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    if not safe:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = f"applemail_{timestamp}"
    if not safe.lower().endswith(".json"):
        safe += ".json"
    return safe


def _extract_first(values: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(values.get(key) or "").strip()
        if text:
            return text
    return ""


def _normalize_mailbox(value: Any) -> str:
    mailbox = str(value or "").strip()
    return mailbox or "INBOX"


def _normalize_record(entry: Any) -> dict[str, str]:
    if isinstance(entry, str):
        return _normalize_text_record(entry)
    if isinstance(entry, (list, tuple)):
        return _normalize_sequence_record(entry)
    if not isinstance(entry, dict):
        raise ValueError(f"不支持的邮箱记录格式: {type(entry).__name__}")

    email = _extract_first(entry, "email", "mail", "address", "username")
    client_id = _extract_first(entry, "client_id", "clientId", "clientID")
    refresh_token = _extract_first(
        entry,
        "refresh_token",
        "refreshToken",
        "rt",
    )
    mailbox = _normalize_mailbox(
        _extract_first(entry, "mailbox", "folder", "mail_folder", "mailFolder")
    )
    password = _extract_first(entry, "password", "pass", "pwd")

    if not email:
        raise ValueError("缺少 email")
    if not client_id or not refresh_token:
        raise ValueError(f"{email} 缺少 client_id 或 refresh_token")

    record = {
        "email": email,
        "client_id": client_id,
        "refresh_token": refresh_token,
        "mailbox": mailbox,
    }
    if password:
        record["password"] = password
    return record


def _normalize_sequence_record(entry: list[Any] | tuple[Any, ...]) -> dict[str, str]:
    values = [str(item or "").strip() for item in entry if str(item or "").strip()]
    if not values:
        raise ValueError("空邮箱记录")
    if len(values) < 3:
        raise ValueError(f"邮箱记录字段不足: {values}")
    if len(values) >= 4:
        email, password, client_id, refresh_token = values[:4]
        record = {
            "email": email,
            "client_id": client_id,
            "refresh_token": refresh_token,
            "mailbox": "INBOX",
        }
        if password:
            record["password"] = password
        if len(values) >= 5 and values[4]:
            record["mailbox"] = _normalize_mailbox(values[4])
        return record

    email, client_id, refresh_token = values[:3]
    record = {
        "email": email,
        "client_id": client_id,
        "refresh_token": refresh_token,
        "mailbox": "INBOX",
    }
    if len(values) >= 4 and values[3]:
        record["mailbox"] = _normalize_mailbox(values[3])
    return record


def _normalize_text_record(line: str) -> dict[str, str]:
    text = str(line or "").strip()
    if not text:
        raise ValueError("空邮箱记录")

    if "----" in text:
        return _normalize_sequence_record(text.split("----"))
    if "\t" in text:
        return _normalize_sequence_record(text.split("\t"))
    return _normalize_sequence_record(text.split())


def _unwrap_json_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items", "accounts", "list", "emails", "mails"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    raise ValueError(f"JSON 根节点必须是对象或数组，当前为 {type(payload).__name__}")


def parse_applemail_pool_content(content: str) -> list[dict[str, str]]:
    text = str(content or "").strip()
    if not text:
        raise ValueError("邮箱池内容为空")

    if text[:1] in {"[", "{"}:
        payload = json.loads(text)
        items = _unwrap_json_records(payload)
        records = [_normalize_record(item) for item in items]
    else:
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        records = [_normalize_text_record(line) for line in lines]

    if not records:
        raise ValueError("邮箱池内容为空")
    return records


def resolve_applemail_pool_path(
    *,
    pool_file: str | None = None,
    pool_dir: str | None = None,
) -> Path:
    base_dir = _normalize_pool_dir(pool_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    raw_file = str(pool_file or "").strip()
    if raw_file:
        file_path = Path(raw_file)
        if file_path.is_absolute():
            resolved = file_path
        else:
            resolved = base_dir / file_path.name
            if not resolved.exists():
                fallback = _project_root() / raw_file
                if fallback.exists():
                    resolved = fallback
        if not resolved.exists():
            raise RuntimeError(f"小苹果邮箱池文件不存在: {resolved}")
        return resolved

    candidates = [
        path
        for pattern in ("*.json", "*.txt", "*.csv")
        for path in base_dir.glob(pattern)
        if path.is_file()
    ]
    if not candidates:
        raise RuntimeError(f"mail 目录下未找到可用的小苹果邮箱池文件: {base_dir}")
    candidates.sort(key=lambda item: (item.stat().st_mtime, item.name), reverse=True)
    return candidates[0]


def load_applemail_pool_records(
    *,
    pool_file: str | None = None,
    pool_dir: str | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    path = resolve_applemail_pool_path(pool_file=pool_file, pool_dir=pool_dir)
    content = path.read_text(encoding="utf-8", errors="ignore")
    records = parse_applemail_pool_content(content)
    return path, records


def load_applemail_pool_snapshot(
    *,
    pool_file: str | None = None,
    pool_dir: str | None = None,
    preview_limit: int = 100,
) -> dict[str, Any]:
    path, records = load_applemail_pool_records(pool_file=pool_file, pool_dir=pool_dir)
    limit = max(int(preview_limit or 0), 0)
    items = [
        {
            "index": idx,
            "email": record["email"],
            "mailbox": record.get("mailbox") or "INBOX",
        }
        for idx, record in enumerate(records[:limit], start=1)
    ]
    return {
        "filename": path.name,
        "path": str(path),
        "count": len(records),
        "items": items,
        "truncated": len(records) > limit if limit > 0 else len(records) > 0,
    }


def take_next_applemail_record(
    *,
    pool_file: str | None = None,
    pool_dir: str | None = None,
) -> tuple[Path, dict[str, str]]:
    path, records = load_applemail_pool_records(pool_file=pool_file, pool_dir=pool_dir)
    key = str(path.resolve())
    with _POOL_CURSOR_LOCK:
        index = _POOL_CURSORS.get(key, 0)
        record = records[index % len(records)]
        _POOL_CURSORS[key] = index + 1
    return path, record


def save_applemail_pool_json(
    content: str,
    *,
    pool_dir: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    records = parse_applemail_pool_content(content)
    output_dir = _normalize_pool_dir(pool_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _normalize_filename(filename)
    path = output_dir / safe_name
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "filename": safe_name,
        "path": str(path),
        "count": len(records),
    }
