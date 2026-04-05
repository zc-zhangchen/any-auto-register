"""外部系统同步（自动导入 / 回填）"""

from __future__ import annotations

from typing import Any

from services.chatgpt_sync import (
    _get_account_extra,
    persist_cpa_sync_result,
    persist_sub2api_sync_result,
    upload_chatgpt_account_to_cpa,
)


def _is_config_enabled(value: Any, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "enabled"}


def sync_account(account) -> list[dict[str, Any]]:
    """根据平台将账号同步到外部系统。"""
    from core.config_store import config_store

    platform = getattr(account, "platform", "")
    results: list[dict[str, Any]] = []

    def _build_chatgpt_upload_account():
        class _A:
            pass

        a = _A()
        a.email = account.email
        extra = _get_account_extra(account)
        a.access_token = extra.get("access_token") or account.token
        a.refresh_token = extra.get("refresh_token", "")
        a.id_token = extra.get("id_token", "")
        a.session_token = extra.get("session_token", "")
        a.client_id = extra.get("client_id", "app_EMoamEEZ73f0CkXaXp7hrann")
        return a

    if platform == "chatgpt":
        upload_account = _build_chatgpt_upload_account()

        # 贡献模式优先级最高：开启后仅上传到贡献服务器，避免重复上报到其它平台。
        contribution_enabled = _is_config_enabled(config_store.get("contribution_enabled", "0"))
        if contribution_enabled:
            contribution_url = str(config_store.get("contribution_server_url", "") or "").strip()
            contribution_key = str(config_store.get("contribution_key", "") or "").strip()
            if not contribution_url:
                msg = "Contribution 服务器地址未配置"
                persist_cpa_sync_result(account, False, msg)
                results.append({"name": "Contribution", "ok": False, "msg": msg})
                return results

            ok, msg = upload_chatgpt_account_to_cpa(
                account,
                api_url=contribution_url,
                api_key=contribution_key or None,
            )
            persist_cpa_sync_result(account, ok, msg)
            results.append({"name": "Contribution", "ok": ok, "msg": msg})
            return results

        cpa_url = str(config_store.get("cpa_api_url", "") or "").strip()
        cpa_enabled = _is_config_enabled(
            config_store.get("cpa_enabled", ""),
            default=bool(cpa_url),
        )
        if cpa_enabled and cpa_url:
            ok, msg = upload_chatgpt_account_to_cpa(account)
            persist_cpa_sync_result(account, ok, msg)
            results.append({"name": "CPA", "ok": ok, "msg": msg})

        codex_proxy_url = str(config_store.get("codex_proxy_url", "") or "").strip()
        if codex_proxy_url:
            upload_type = str(config_store.get("codex_proxy_upload_type", "at") or "at").strip().lower()
            extra = _get_account_extra(account)

            class _CP:
                pass

            cp = _CP()
            cp.access_token = extra.get("access_token") or account.token
            cp.refresh_token = extra.get("refresh_token", "")

            if upload_type == "rt":
                from platforms.chatgpt.cpa_upload import upload_to_codex_proxy
                ok, msg = upload_to_codex_proxy(cp)
                results.append({"name": "CodexProxy(RT)", "ok": ok, "msg": msg})
            else:
                from platforms.chatgpt.cpa_upload import upload_at_to_codex_proxy
                ok, msg = upload_at_to_codex_proxy(cp)
                results.append({"name": "CodexProxy(AT)", "ok": ok, "msg": msg})

        # 关键逻辑：ChatGPT 现在支持同时回填 CPA 和 Sub2API，互不覆盖、分别上报结果。
        sub2api_url = str(config_store.get("sub2api_api_url", "") or "").strip()
        sub2api_key = str(config_store.get("sub2api_api_key", "") or "").strip()
        sub2api_enabled = _is_config_enabled(
            config_store.get("sub2api_enabled", ""),
            default=bool(sub2api_url and sub2api_key),
        )
        if sub2api_enabled and sub2api_url and sub2api_key:
            from platforms.chatgpt.sub2api_upload import upload_to_sub2api

            ok, msg = upload_to_sub2api(
                upload_account,
                api_url=sub2api_url,
                api_key=sub2api_key,
            )
            persist_sub2api_sync_result(account, ok, msg)
            results.append({"name": "Sub2API", "ok": ok, "msg": msg})

    elif platform == "grok":
        grok2api_url = str(config_store.get("grok2api_url", "") or "").strip()
        if grok2api_url:
            from services.grok2api_runtime import ensure_grok2api_ready
            from platforms.grok.grok2api_upload import upload_to_grok2api

            ready, ready_msg = ensure_grok2api_ready()
            if not ready:
                results.append({"name": "grok2api", "ok": False, "msg": ready_msg})
                return results

            ok, msg = upload_to_grok2api(account)
            results.append({"name": "grok2api", "ok": ok, "msg": msg})

    elif platform == "kiro":
        from platforms.kiro.account_manager_upload import resolve_manager_path, upload_to_kiro_manager

        configured_path = str(config_store.get("kiro_manager_path", "") or "").strip()
        target_path = resolve_manager_path(configured_path or None)
        if configured_path or target_path.parent.exists() or target_path.exists():
            ok, msg = upload_to_kiro_manager(account, path=configured_path or None)
            results.append({"name": "Kiro Manager", "ok": ok, "msg": msg})

    return results
