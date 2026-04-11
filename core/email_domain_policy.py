"""邮箱域名全局策略校验。"""

from __future__ import annotations

import re
from typing import Any


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _required_level_count(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 2
    try:
        level_count = int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("域名级数必须是整数") from exc
    if level_count < 2:
        raise ValueError("域名级数不能小于 2")
    return level_count


def validate_email_domain_policy(email: str, config: dict[str, Any] | None = None) -> None:
    cfg = config or {}
    if not _to_bool(cfg.get("email_domain_rule_enabled")):
        return

    address = str(email or "").strip().lower()
    if "@" not in address:
        raise ValueError("邮箱格式无效，缺少域名")

    _, domain = address.rsplit("@", 1)
    domain = domain.strip().strip(".")
    if not domain:
        raise ValueError("邮箱格式无效，缺少域名")

    levels = [part for part in domain.split(".") if part]
    required_levels = _required_level_count(cfg.get("email_domain_level_count"))
    if len(levels) < required_levels:
        raise ValueError(
            f"邮箱域名不满足要求：当前 {len(levels)} 级，至少需要 {required_levels} 级"
        )

    letters = len(re.findall(r"[a-z]", domain))
    digits = len(re.findall(r"\d", domain))
    if letters < 2 or digits < 2:
        raise ValueError("邮箱域名不满足要求：域名至少包含 2 个英文字母和 2 个数字")
