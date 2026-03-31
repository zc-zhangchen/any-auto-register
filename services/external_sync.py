"""外部系统同步（自动导入 / 回填）"""

from __future__ import annotations

from typing import Any


def sync_account(account) -> list[dict[str, Any]]:
    """根据平台将账号同步到外部系统。"""
    from core.config_store import config_store

    platform = getattr(account, "platform", "")
    results: list[dict[str, Any]] = []

    if platform == "chatgpt":
        from platforms.chatgpt.cpa_upload import (
            generate_token_json,
            save_token_json_file,
            upload_to_cpa,
        )

        class _A:
            pass

        a = _A()
        a.email = account.email
        extra = account.extra or {}
        a.access_token = extra.get("access_token") or account.token
        a.refresh_token = extra.get("refresh_token", "")
        a.id_token = extra.get("id_token", "")

        token_data = generate_token_json(a)
        token_path = save_token_json_file(token_data)
        results.append({"name": "CPA File", "ok": True, "msg": f"已写入 {token_path}"})

        cpa_url = config_store.get("cpa_api_url", "")
        if cpa_url:
            ok, msg = upload_to_cpa(token_data)
            results.append({"name": "CPA", "ok": ok, "msg": msg})

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
