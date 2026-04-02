from fastapi import APIRouter
from pydantic import BaseModel
from core.config_store import config_store

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_KEYS = [
    "laoudo_auth", "laoudo_email", "laoudo_account_id",
    "yescaptcha_key", "twocaptcha_key",
    "default_executor", "default_captcha_solver",
    "duckmail_api_url", "duckmail_provider_url", "duckmail_bearer",
    "freemail_api_url", "freemail_admin_token", "freemail_username", "freemail_password", "freemail_domain_index", "freemail_length",
    "moemail_api_url",
    "mail_provider",
    "cfworker_api_url", "cfworker_admin_token", "cfworker_domain", "cfworker_fingerprint",
    "luckmail_base_url", "luckmail_api_key", "luckmail_email_type", "luckmail_domain",
    "cpa_api_url", "cpa_api_key",
    "team_manager_url", "team_manager_key",
    "cliproxyapi_management_key",
    "grok2api_url", "grok2api_app_key", "grok2api_pool", "grok2api_quota",
    "kiro_manager_path", "kiro_manager_exe",
]


class ConfigUpdate(BaseModel):
    data: dict


@router.get("")
def get_config():
    all_cfg = config_store.get_all()
    # 只返回已知 key，未设置的返回空字符串
    return {k: all_cfg.get(k, "") for k in CONFIG_KEYS}


@router.put("")
def update_config(body: ConfigUpdate):
    # 只允许更新已知 key
    safe = {k: v for k, v in body.data.items() if k in CONFIG_KEYS}
    config_store.set_many(safe)
    return {"ok": True, "updated": list(safe.keys())}
