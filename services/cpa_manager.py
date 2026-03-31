"""CPA 凭证维护：清理异常凭证并在低于阈值时自动补注册。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_THRESHOLD = 5
DEFAULT_CONCURRENCY = 1
DEFAULT_REGISTER_DELAY_SECONDS = 0.0
AUTO_REGISTER_SOURCE = "cpa_replenish"


@dataclass
class CpaMaintenanceConfig:
    enabled: bool
    interval_minutes: int
    threshold: int
    concurrency: int
    register_delay_seconds: float


def _get_config_store():
    from core.config_store import config_store

    return config_store


def _to_bool(value: str | None, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: str | None, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(float(str(value or "").strip())))
    except Exception:
        return default


def _to_float(value: str | None, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(str(value or "").strip()))
    except Exception:
        return default


def get_cpa_maintenance_config() -> CpaMaintenanceConfig:
    config_store = _get_config_store()
    return CpaMaintenanceConfig(
        enabled=_to_bool(config_store.get("cpa_cleanup_enabled", ""), default=False),
        interval_minutes=_to_int(
            config_store.get("cpa_cleanup_interval_minutes", ""),
            DEFAULT_INTERVAL_MINUTES,
            minimum=1,
        ),
        threshold=_to_int(
            config_store.get("cpa_cleanup_threshold", ""),
            DEFAULT_THRESHOLD,
            minimum=1,
        ),
        concurrency=_to_int(
            config_store.get("cpa_cleanup_concurrency", ""),
            DEFAULT_CONCURRENCY,
            minimum=1,
        ),
        register_delay_seconds=_to_float(
            config_store.get("cpa_cleanup_register_delay_seconds", ""),
            DEFAULT_REGISTER_DELAY_SECONDS,
            minimum=0.0,
        ),
    )


def get_cpa_maintenance_interval_seconds() -> int:
    config_store = _get_config_store()
    api_url = str(config_store.get("cpa_api_url", "") or "").strip()
    config = get_cpa_maintenance_config()
    if not config.enabled or not api_url:
        return 0
    return config.interval_minutes * 60


def _api_base(api_url: str | None = None) -> str:
    config_store = _get_config_store()
    base_url = str(api_url or config_store.get("cpa_api_url", "") or "").strip()
    if not base_url:
        raise RuntimeError("CPA API URL 未配置")
    return base_url.rstrip("/")


def _headers(api_key: str | None = None) -> dict[str, str]:
    config_store = _get_config_store()
    token = str(api_key or config_store.get("cpa_api_key", "") or "").strip()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(method: str, path: str, *, api_url: str | None = None, api_key: str | None = None, json_body: dict | None = None) -> Any:
    response = requests.request(
        method,
        f"{_api_base(api_url)}{path}",
        headers=_headers(api_key),
        json=json_body,
        timeout=30,
        verify=False,
    )
    response.raise_for_status()
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return response.text


def list_auth_files(*, api_url: str | None = None, api_key: str | None = None) -> list[dict[str, Any]]:
    data = _request("GET", "/v0/management/auth-files", api_url=api_url, api_key=api_key)
    files = data.get("files", []) if isinstance(data, dict) else []
    return [item for item in files if isinstance(item, dict)]


def delete_auth_files(names: list[str], *, api_url: str | None = None, api_key: str | None = None) -> Any:
    clean_names = [name for name in names if str(name).strip()]
    if not clean_names:
        return {"deleted": 0}
    return _request(
        "DELETE",
        "/v0/management/auth-files",
        api_url=api_url,
        api_key=api_key,
        json_body={"names": clean_names},
    )


def _count_remaining(files: list[dict[str, Any]]) -> int:
    return sum(
        1
        for item in files
        if str(item.get("name", "")).strip() and str(item.get("status", "")).strip().lower() != "error"
    )


def _error_names(files: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(item.get("name", "")).strip()
            for item in files
            if str(item.get("status", "")).strip().lower() == "error" and str(item.get("name", "")).strip()
        }
    )


def _normalize_executor(executor: str | None) -> str:
    value = str(executor or "").strip()
    if value in {"protocol", "headless", "headed"}:
        return value
    return "protocol"


def _normalize_solver(solver: str | None) -> str:
    value = str(solver or "").strip()
    if value in {"yescaptcha", "local_solver", "manual"}:
        return value
    return "yescaptcha"


def _trigger_register(missing_count: int, *, config: CpaMaintenanceConfig, remaining_count: int) -> dict[str, Any]:
    from api.tasks import RegisterTaskRequest, enqueue_register_task, has_active_register_task

    if has_active_register_task(platform="chatgpt", source=AUTO_REGISTER_SOURCE):
        print("[CPA] 已存在进行中的自动补注册任务，跳过本轮补注册")
        return {"triggered": False, "reason": "task_running"}

    config_store = _get_config_store()
    req = RegisterTaskRequest(
        platform="chatgpt",
        count=missing_count,
        concurrency=config.concurrency,
        register_delay_seconds=config.register_delay_seconds,
        executor_type=_normalize_executor(config_store.get("default_executor", "protocol")),
        captcha_solver=_normalize_solver(config_store.get("default_captcha_solver", "yescaptcha")),
        extra={},
    )
    task_id = enqueue_register_task(
        req,
        source=AUTO_REGISTER_SOURCE,
        meta={
            "remaining": remaining_count,
            "threshold": config.threshold,
            "missing": missing_count,
        },
    )
    print(
        f"[CPA] 剩余凭证 {remaining_count} 低于阈值 {config.threshold}，"
        f"已创建自动注册任务 {task_id}，补充 {missing_count} 个"
    )
    return {"triggered": True, "task_id": task_id}


def maintain_cpa_credentials() -> dict[str, Any]:
    config = get_cpa_maintenance_config()
    if not config.enabled:
        return {"ok": False, "reason": "disabled"}

    files = list_auth_files()
    error_names = _error_names(files)
    deleted_count = 0

    if error_names:
        delete_auth_files(error_names)
        deleted_count = len(error_names)
        print(f"[CPA] 已删除 {deleted_count} 个 status=error 的凭证")
        files = list_auth_files()

    remaining_count = _count_remaining(files)
    result: dict[str, Any] = {
        "ok": True,
        "deleted": deleted_count,
        "remaining": remaining_count,
        "threshold": config.threshold,
    }

    if remaining_count >= config.threshold:
        print(f"[CPA] 剩余凭证 {remaining_count}，阈值 {config.threshold}，无需补注册")
        result["register"] = {"triggered": False, "reason": "enough_credentials"}
        return result

    missing_count = config.threshold - remaining_count
    result["register"] = _trigger_register(
        missing_count,
        config=config,
        remaining_count=remaining_count,
    )
    return result
