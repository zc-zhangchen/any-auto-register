from __future__ import annotations

"""全局配置持久化 - 存储在 SQLite，并在缺省时回退到环境变量/.env。"""
import os
import re
from pathlib import Path
from typing import Optional
from sqlmodel import Field, SQLModel, Session, select
from .db import engine


_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _normalize_config_value(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _canonical_config_key(key: str) -> str:
    value = str(key or "").strip()
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _config_key_candidates(key: str) -> list[str]:
    raw = str(key or "").strip()
    if not raw:
        return []

    normalized = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_")
    candidates: list[str] = []
    seen = set()
    for item in (
        raw,
        raw.lower(),
        raw.upper(),
        normalized,
        normalized.lower(),
        normalized.upper(),
    ):
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)
    return candidates


def _load_env_file(path: Path | str | None = None) -> dict[str, str]:
    env_path = Path(path or _ENV_FILE)
    if not env_path.exists():
        return {}

    try:
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return {}

    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _normalize_config_value(value)
    return values


def _runtime_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in _load_env_file().items():
        text = _normalize_config_value(value)
        if text:
            values[key] = text
    for key, value in os.environ.items():
        text = _normalize_config_value(value)
        if text:
            values[key] = text
    return values


def _get_env_fallback_value(key: str, env_values: Optional[dict[str, str]] = None) -> str:
    values = env_values if env_values is not None else _runtime_env_values()
    for candidate in _config_key_candidates(key):
        text = str(values.get(candidate, "") or "").strip()
        if text:
            return text
    return ""


def _merge_env_fallback(values: dict[str, str], env_values: Optional[dict[str, str]] = None) -> dict[str, str]:
    merged = dict(values or {})
    runtime_values = env_values if env_values is not None else _runtime_env_values()
    for env_key, env_value in runtime_values.items():
        text = str(env_value or "").strip()
        if not text:
            continue
        canonical_key = _canonical_config_key(env_key)
        for target_key in (env_key, canonical_key):
            if not target_key:
                continue
            if str(merged.get(target_key, "") or "").strip():
                continue
            merged[target_key] = text
    return merged


class ConfigItem(SQLModel, table=True):
    __tablename__ = "configs"
    key: str = Field(primary_key=True)
    value: str = ""


class ConfigStore:
    """简单 key-value 配置存储"""

    def get(self, key: str, default: str = "") -> str:
        env_values = _runtime_env_values()
        with Session(engine) as s:
            item = s.get(ConfigItem, key)
            value = str(item.value if item else "" or "").strip()
            if value:
                return value
        fallback = _get_env_fallback_value(key, env_values=env_values)
        return fallback or default

    def set(self, key: str, value: str) -> None:
        with Session(engine) as s:
            item = s.get(ConfigItem, key)
            if item:
                item.value = value
            else:
                item = ConfigItem(key=key, value=value)
            s.add(item)
            s.commit()

    def get_all(self) -> dict:
        with Session(engine) as s:
            items = s.exec(select(ConfigItem)).all()
            values = {i.key: i.value for i in items}
        return _merge_env_fallback(values)

    def set_many(self, data: dict) -> None:
        with Session(engine) as s:
            for key, value in data.items():
                item = s.get(ConfigItem, key)
                if item:
                    item.value = value
                else:
                    item = ConfigItem(key=key, value=value)
                s.add(item)
            s.commit()


config_store = ConfigStore()
