from fastapi import APIRouter
from pydantic import BaseModel
import json
from pathlib import Path
from core.config_store import config_store

router = APIRouter(prefix="/config", tags=["config"])

DEFAULT_MALIAPI_BASE_URL = "https://maliapi.215.im/v1"
DEFAULT_MALIAPI_AUTO_DOMAIN_STRATEGY = "balanced"
_DEFAULT_YYDS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "codex_yyds_register" / "config.json"

CONFIG_KEYS = [
    "laoudo_auth",
    "laoudo_email",
    "laoudo_account_id",
    "yescaptcha_key",
    "twocaptcha_key",
    "default_executor",
    "default_captcha_solver",
    "duckmail_api_url",
    "duckmail_provider_url",
    "duckmail_bearer",
    "duckmail_domain",
    "duckmail_api_key",
    "freemail_api_url",
    "freemail_admin_token",
    "freemail_username",
    "freemail_password",
    "moemail_api_url",
    "skymail_api_base",
    "skymail_token",
    "skymail_domain",
    "mail_provider",
    "maliapi_base_url",
    "maliapi_api_key",
    "maliapi_domain",
    "maliapi_auto_domain_strategy",
    "cfworker_api_url",
    "cfworker_admin_token",
    "cfworker_custom_auth",
    "cfworker_domain",
    "cfworker_domains",
    "cfworker_enabled_domains",
    "cfworker_fingerprint",
    "facai_api_url",
    "facai_domain",
    "smstome_cookie",
    "smstome_country_slugs",
    "smstome_phone_attempts",
    "smstome_otp_timeout_seconds",
    "smstome_poll_interval_seconds",
    "smstome_sync_max_pages_per_country",
    "luckmail_base_url",
    "luckmail_api_key",
    "luckmail_email_type",
    "luckmail_domain",
    "cpa_api_url",
    "cpa_api_key",
    "cpa_cleanup_enabled",
    "cpa_cleanup_interval_minutes",
    "cpa_cleanup_threshold",
    "cpa_cleanup_concurrency",
    "cpa_cleanup_register_delay_seconds",
    "sub2api_api_url",
    "sub2api_api_key",
    "team_manager_url",
    "team_manager_key",
    "codex_proxy_url",
    "codex_proxy_key",
    "codex_proxy_upload_type",
    "cliproxyapi_management_key",
    "grok2api_url",
    "grok2api_app_key",
    "grok2api_pool",
    "grok2api_quota",
    "kiro_manager_path",
    "kiro_manager_exe",
]


class ConfigUpdate(BaseModel):
    data: dict


def _load_codex_yyds_mail_defaults(config_path: Path | None = None) -> dict[str, str]:
    path = Path(config_path or _DEFAULT_YYDS_CONFIG_PATH)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    return {
        "maliapi_base_url": str(payload.get("yydsmail_api_base", "") or "").strip(),
        "maliapi_api_key": str(payload.get("yydsmail_api_key", "") or "").strip(),
    }


def _apply_default_config_values(values: dict, *, yyds_config_path: Path | None = None) -> dict:
    merged = dict(values or {})
    yyds_defaults = _load_codex_yyds_mail_defaults(yyds_config_path)

    if not str(merged.get("maliapi_base_url", "") or "").strip():
        merged["maliapi_base_url"] = yyds_defaults.get("maliapi_base_url") or DEFAULT_MALIAPI_BASE_URL
    if not str(merged.get("maliapi_api_key", "") or "").strip():
        merged["maliapi_api_key"] = yyds_defaults.get("maliapi_api_key", "")
    if not str(merged.get("maliapi_auto_domain_strategy", "") or "").strip():
        merged["maliapi_auto_domain_strategy"] = DEFAULT_MALIAPI_AUTO_DOMAIN_STRATEGY

    return merged


@router.get("")
def get_config():
    all_cfg = _apply_default_config_values(config_store.get_all())
    # 只返回已知 key，未设置的返回空字符串
    return {k: all_cfg.get(k, "") for k in CONFIG_KEYS}


@router.put("")
def update_config(body: ConfigUpdate):
    # 只允许更新已知 key
    safe = {k: v for k, v in body.data.items() if k in CONFIG_KEYS}
    config_store.set_many(safe)
    return {"ok": True, "updated": list(safe.keys())}
