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


def _pick_text(source: Any, *keys: str, default: str = "") -> str:
    if not isinstance(source, dict):
        return default
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        text = value.strip() if isinstance(value, str) else str(value).strip()
        if text:
            return text
    return default


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
        a.access_token = _pick_text(extra, "access_token", "accessToken") or account.token
        a.refresh_token = _pick_text(extra, "refresh_token", "refreshToken")
        a.id_token = _pick_text(extra, "id_token", "idToken")
        a.session_token = _pick_text(extra, "session_token", "sessionToken")
        a.client_id = _pick_text(extra, "client_id", "clientId", default="app_EMoamEEZ73f0CkXaXp7hrann")
        return a

    if platform == "chatgpt":
        upload_account = _build_chatgpt_upload_account()

        # 贡献模式优先级最高：开启后仅上传到贡献服务器，避免重复上报到其它平台。
        contribution_enabled = _is_config_enabled(config_store.get("contribution_enabled", "0"))
        if contribution_enabled:
            contribution_mode = str(config_store.get("contribution_mode", "codex") or "codex").strip().lower()

            if contribution_mode == "custom":
                # 自定义贡献系统模式
                custom_url = str(config_store.get("custom_contribution_url", "") or "").strip()
                custom_token = str(config_store.get("custom_contribution_token", "") or "").strip()
                if not custom_url:
                    msg = "自定义贡献服务器地址未配置"
                    persist_cpa_sync_result(account, False, msg)
                    results.append({"name": "CustomContribution", "ok": False, "msg": msg})
                    return results
                if not custom_token:
                    msg = "自定义贡献系统 token 未配置（请先绑定邮箱）"
                    persist_cpa_sync_result(account, False, msg)
                    results.append({"name": "CustomContribution", "ok": False, "msg": msg})
                    return results

                try:
                    import requests
                    from platforms.chatgpt.cpa_upload import generate_token_json

                    # 生成完整的 token JSON
                    extra = _get_account_extra(account)
                    token_json = generate_token_json(account)

                    # 如果 token_json 中没有 refresh_token，从 extra 获取
                    if not token_json.get("refresh_token"):
                        refresh_token = _pick_text(extra, "refresh_token", "refreshToken")
                        print(f"[DEBUG] extra keys: {list(extra.keys())}")
                        print(f"[DEBUG] refresh_token from extra: {refresh_token[:20] if refresh_token else 'EMPTY'}")
                        if refresh_token:
                            token_json["refresh_token"] = refresh_token
                    if not token_json.get("access_token"):
                        access_token = _pick_text(extra, "access_token", "accessToken") or getattr(account, "token", "")
                        if access_token:
                            token_json["access_token"] = access_token
                    if not token_json.get("id_token"):
                        id_token = _pick_text(extra, "id_token", "idToken")
                        if id_token:
                            token_json["id_token"] = id_token
                    if not token_json.get("client_id"):
                        client_id = _pick_text(extra, "client_id", "clientId")
                        if client_id:
                            token_json["client_id"] = client_id

                    refresh_token = str(token_json.get("refresh_token") or "").strip()
                    access_token = str(token_json.get("access_token") or "").strip()

                    # 验证必须有 refresh_token
                    print(f"[DEBUG] Final token_json keys: {list(token_json.keys())}")
                    print(f"[DEBUG] Final refresh_token: {refresh_token[:20] if refresh_token else 'EMPTY'}")
                    if not refresh_token:
                        msg = "账号缺少 refresh_token"
                        persist_cpa_sync_result(account, False, msg)
                        results.append({"name": "CustomContribution", "ok": False, "msg": msg})
                        return results

                    resp = requests.post(
                        f"{custom_url.rstrip('/')}/api/upload",
                        json={
                            "email": account.email,
                            "refresh_token": refresh_token,
                            "access_token": access_token,
                            "token_json": token_json,
                        },
                        headers={"Authorization": f"Bearer {custom_token}"},
                        timeout=15,
                    )
                    data = resp.json()
                    if resp.status_code >= 400:
                        msg = data.get("error") or data.get("message") or str(data)
                        persist_cpa_sync_result(account, False, msg)
                        results.append({"name": "CustomContribution", "ok": False, "msg": msg})
                        return results

                    msg = f"上传成功: {data.get('message', '')}"
                    persist_cpa_sync_result(account, True, msg)
                    results.append({"name": "CustomContribution", "ok": True, "msg": msg})
                    return results
                except Exception as exc:
                    msg = f"上传到自定义贡献系统失败: {exc}"
                    persist_cpa_sync_result(account, False, msg)
                    results.append({"name": "CustomContribution", "ok": False, "msg": msg})
                    return results
            else:
                # codex2api 模式（原有逻辑）
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
            cp.access_token = _pick_text(extra, "access_token", "accessToken") or account.token
            cp.refresh_token = _pick_text(extra, "refresh_token", "refreshToken")

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
