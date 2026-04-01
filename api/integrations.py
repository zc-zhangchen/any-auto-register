from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.base_platform import Account, AccountStatus
from core.db import AccountModel, engine
from services.external_apps import install, list_status, start, start_all, stop, stop_all
from services.chatgpt_sync import backfill_chatgpt_account_to_cpa, get_cliproxy_sync_state

router = APIRouter(prefix="/integrations", tags=["integrations"])


class BackfillRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["grok", "kiro"])
    account_ids: list[int] = Field(default_factory=list)
    pending_only: bool = False
    status: Optional[str] = None
    email: Optional[str] = None


def _to_account(model: AccountModel) -> Account:
    return Account(
        platform=model.platform,
        email=model.email,
        password=model.password,
        user_id=model.user_id,
        region=model.region,
        token=model.token,
        status=AccountStatus(model.status),
        extra=model.get_extra(),
    )


@router.get("/services")
def get_services():
    return {"items": list_status()}


@router.post("/services/start-all")
def start_all_services():
    return {"items": start_all()}


@router.post("/services/stop-all")
def stop_all_services():
    return {"items": stop_all()}


@router.post("/services/{name}/start")
def start_service(name: str):
    return start(name)


@router.post("/services/{name}/install")
def install_service(name: str):
    return install(name)


@router.post("/services/{name}/stop")
def stop_service(name: str):
    return stop(name)


@router.post("/backfill")
def backfill_integrations(body: BackfillRequest):
    summary = {"total": 0, "success": 0, "failed": 0, "skipped": 0, "items": []}
    targets = set(body.platforms or [])

    with Session(engine) as s:
        q = select(AccountModel)
        if body.account_ids:
            q = q.where(AccountModel.id.in_(body.account_ids))
            if targets:
                q = q.where(AccountModel.platform.in_(targets))
        elif targets:
            q = q.where(AccountModel.platform.in_(targets))
        else:
            return summary

        if body.status:
            q = q.where(AccountModel.status == body.status)
        if body.email:
            q = q.where(AccountModel.email.contains(body.email))

        rows = s.exec(q).all()
        if body.pending_only:
            rows = [
                row for row in rows
                if row.platform != "chatgpt"
                or str(get_cliproxy_sync_state(row).get("remote_state") or "").strip().lower() == "not_found"
            ]

        if any(row.platform == "grok" for row in rows):
            from services.grok2api_runtime import ensure_grok2api_ready

            ok, msg = ensure_grok2api_ready()
            if not ok:
                return {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "items": [{"platform": "grok", "email": "", "results": [{"name": "grok2api", "ok": False, "msg": msg}]}],
                }

        for row in rows:
            item = {"platform": row.platform, "email": row.email, "results": []}
            try:
                results = []
                if row.platform == "chatgpt":
                    outcome = backfill_chatgpt_account_to_cpa(row, session=s, commit=True)
                    ok = bool(outcome.get("ok"))
                    skipped = bool(outcome.get("skipped"))
                    results.extend(outcome.get("results") or [])
                    if not results:
                        results.append({"name": "CLIProxyAPI", "ok": ok, "msg": outcome.get("message", "")})
                    if skipped:
                        summary["skipped"] += 1
                    elif ok:
                        summary["success"] += 1
                    else:
                        summary["failed"] += 1

                elif row.platform == "grok":
                    from core.config_store import config_store
                    from platforms.grok.grok2api_upload import upload_to_grok2api

                    account = _to_account(row)
                    api_url = str(config_store.get("grok2api_url", "") or "").strip() or "http://127.0.0.1:8011"
                    app_key = str(config_store.get("grok2api_app_key", "") or "").strip() or "grok2api"
                    ok, msg = upload_to_grok2api(account, api_url=api_url, app_key=app_key)
                    results.append({"name": "grok2api", "ok": ok, "msg": msg})

                elif row.platform == "kiro":
                    from core.config_store import config_store
                    from platforms.kiro.account_manager_upload import upload_to_kiro_manager

                    account = _to_account(row)
                    configured_path = str(config_store.get("kiro_manager_path", "") or "").strip() or None
                    ok, msg = upload_to_kiro_manager(account, path=configured_path)
                    results.append({"name": "Kiro Manager", "ok": ok, "msg": msg})

                if not results:
                    item["results"].append({"name": "skip", "ok": False, "msg": "未配置对应导入目标"})
                    summary["failed"] += 1
                else:
                    item["results"] = results
                    if row.platform != "chatgpt":
                        if all(r.get("ok") for r in results):
                            summary["success"] += 1
                        else:
                            summary["failed"] += 1
            except Exception as e:
                s.rollback()
                item["results"].append({"name": "error", "ok": False, "msg": str(e)})
                summary["failed"] += 1
            summary["items"].append(item)
            summary["total"] += 1

    return summary
