from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from typing import Optional
from copy import deepcopy
from datetime import datetime, timezone
from core.db import TaskLog, TaskRunModel, engine
from core.task_runtime import (
    AttemptOutcome,
    AttemptResult,
    RegisterTaskStore,
    SkipCurrentAttemptRequested,
    StopTaskRequested,
)
import time, json, asyncio, threading, logging

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)

MAX_FINISHED_TASKS = 200
CLEANUP_THRESHOLD = 250
_task_store = RegisterTaskStore(
    max_finished_tasks=MAX_FINISHED_TASKS,
    cleanup_threshold=CLEANUP_THRESHOLD,
)


class RegisterTaskRequest(BaseModel):
    platform: str
    email: Optional[str] = None
    password: Optional[str] = None
    count: int = 1
    concurrency: int = 1
    register_delay_seconds: float = 0
    proxy: Optional[str] = None
    executor_type: str = "protocol"
    captcha_solver: str = "yescaptcha"
    extra: dict = Field(default_factory=dict)


class TaskLogBatchDeleteRequest(BaseModel):
    ids: list[int]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value, fallback):
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return json.dumps(fallback, ensure_ascii=False)


def _json_loads(raw: str, fallback):
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


def _to_epoch_seconds(value) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _to_datetime(value) -> datetime:
    try:
        ts = float(value or 0)
        if ts > 1_000_000_000_000:
            ts /= 1000
        if ts <= 0:
            return _utcnow()
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return _utcnow()


def _normalize_snapshot(snapshot: dict) -> dict:
    return {
        "id": str(snapshot.get("id") or ""),
        "status": str(snapshot.get("status") or "pending"),
        "platform": str(snapshot.get("platform") or ""),
        "source": str(snapshot.get("source") or "manual"),
        "meta": snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else {},
        "total": int(snapshot.get("total") or 0),
        "progress": str(snapshot.get("progress") or "0/0"),
        "logs": snapshot.get("logs") if isinstance(snapshot.get("logs"), list) else [],
        "success": int(snapshot.get("success") or 0),
        "registered": int(snapshot.get("registered") or 0),
        "skipped": int(snapshot.get("skipped") or 0),
        "errors": snapshot.get("errors") if isinstance(snapshot.get("errors"), list) else [],
        "control": snapshot.get("control") if isinstance(snapshot.get("control"), dict) else {},
        "cashier_urls": snapshot.get("cashier_urls") if isinstance(snapshot.get("cashier_urls"), list) else [],
        "error": str(snapshot.get("error") or ""),
        "created_at": _to_epoch_seconds(snapshot.get("created_at")),
        "updated_at": _to_epoch_seconds(snapshot.get("updated_at")),
    }


def _task_run_to_snapshot(row: TaskRunModel) -> dict:
    return _normalize_snapshot(
        {
            "id": row.id,
            "status": row.status,
            "platform": row.platform,
            "source": row.source,
            "meta": _json_loads(row.meta_json, {}),
            "total": row.total,
            "progress": row.progress,
            "logs": _json_loads(row.logs_json, []),
            "success": row.success,
            "registered": row.registered,
            "skipped": row.skipped,
            "errors": _json_loads(row.errors_json, []),
            "control": _json_loads(row.control_json, {}),
            "cashier_urls": _json_loads(row.cashier_urls_json, []),
            "error": row.error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _upsert_task_run(snapshot: dict) -> None:
    normalized = _normalize_snapshot(snapshot)
    if not normalized["id"]:
        return
    with Session(engine) as s:
        row = s.get(TaskRunModel, normalized["id"])
        if row is None:
            row = TaskRunModel(
                id=normalized["id"],
                platform=normalized["platform"],
                source=normalized["source"],
                status=normalized["status"],
                total=normalized["total"],
                progress=normalized["progress"],
                success=normalized["success"],
                registered=normalized["registered"],
                skipped=normalized["skipped"],
                error=normalized["error"],
                meta_json=_json_dumps(normalized["meta"], {}),
                logs_json=_json_dumps(normalized["logs"], []),
                errors_json=_json_dumps(normalized["errors"], []),
                cashier_urls_json=_json_dumps(normalized["cashier_urls"], []),
                control_json=_json_dumps(normalized["control"], {}),
                created_at=_to_datetime(normalized["created_at"]),
                updated_at=_to_datetime(normalized["updated_at"]),
            )
            s.add(row)
        else:
            row.platform = normalized["platform"]
            row.source = normalized["source"]
            row.status = normalized["status"]
            row.total = normalized["total"]
            row.progress = normalized["progress"]
            row.success = normalized["success"]
            row.registered = normalized["registered"]
            row.skipped = normalized["skipped"]
            row.error = normalized["error"]
            row.meta_json = _json_dumps(normalized["meta"], {})
            row.logs_json = _json_dumps(normalized["logs"], [])
            row.errors_json = _json_dumps(normalized["errors"], [])
            row.cashier_urls_json = _json_dumps(normalized["cashier_urls"], [])
            row.control_json = _json_dumps(normalized["control"], {})
            if row.created_at is None:
                row.created_at = _to_datetime(normalized["created_at"])
            row.updated_at = _to_datetime(normalized["updated_at"])
            s.add(row)
        s.commit()


def _persist_task_snapshot(task_id: str) -> None:
    if not _task_store.exists(task_id):
        return
    try:
        snapshot = _task_store.snapshot(task_id)
    except Exception:
        return
    _upsert_task_run(snapshot)


def _get_persisted_task(task_id: str) -> Optional[dict]:
    with Session(engine) as s:
        row = s.get(TaskRunModel, task_id)
        if row is None:
            return None
        return _task_run_to_snapshot(row)


def _list_persisted_tasks() -> list[dict]:
    with Session(engine) as s:
        rows = s.exec(select(TaskRunModel)).all()
    snapshots = [_task_run_to_snapshot(row) for row in rows]
    snapshots.sort(
        key=lambda item: (
            {"running": 0, "pending": 1, "done": 2, "failed": 3, "stopped": 4}.get(
                str(item.get("status") or ""),
                9,
            ),
            -_to_epoch_seconds(item.get("created_at")),
        )
    )
    return snapshots


def _finalize_orphan_tasks() -> None:
    with Session(engine) as s:
        rows = s.exec(
            select(TaskRunModel).where(TaskRunModel.status.in_(["pending", "running"]))
        ).all()
        if not rows:
            return
        changed = False
        for row in rows:
            if _task_store.exists(row.id):
                continue
            row.status = "stopped"
            row.error = row.error or "任务因服务重启中断"
            logs = _json_loads(row.logs_json, [])
            tip = "[SYSTEM] 任务因服务重启中断，已自动标记为已停止"
            if tip not in logs:
                ts = datetime.now().strftime("%H:%M:%S")
                logs.append(f"[{ts}] {tip}")
            row.logs_json = _json_dumps(logs, [])
            row.updated_at = _utcnow()
            s.add(row)
            changed = True
        if changed:
            s.commit()


def _ensure_task_exists(task_id: str) -> None:
    if _task_store.exists(task_id):
        return
    if _get_persisted_task(task_id) is None:
        raise HTTPException(404, "任务不存在")


def _ensure_task_mutable(task_id: str) -> None:
    _ensure_task_exists(task_id)
    if _task_store.exists(task_id):
        snapshot = _task_store.snapshot(task_id)
    else:
        snapshot = _get_persisted_task(task_id) or {}
    if snapshot.get("status") in {"done", "failed", "stopped"}:
        raise HTTPException(409, "任务已结束，无法再执行控制操作")


def _get_task_snapshot(task_id: str) -> dict:
    _ensure_task_exists(task_id)
    if _task_store.exists(task_id):
        _persist_task_snapshot(task_id)
    snapshot = _get_persisted_task(task_id)
    if snapshot is None and _task_store.exists(task_id):
        snapshot = _normalize_snapshot(_task_store.snapshot(task_id))
    if snapshot is None:
        raise HTTPException(404, "任务不存在")
    return snapshot


def _prepare_register_request(req: RegisterTaskRequest) -> RegisterTaskRequest:
    from core.config_store import config_store

    req_data = req.model_dump()
    req_data["extra"] = deepcopy(req_data.get("extra") or {})
    prepared = RegisterTaskRequest(**req_data)

    mail_provider = prepared.extra.get("mail_provider") or config_store.get(
        "mail_provider", ""
    )
    if mail_provider == "luckmail":
        platform = prepared.platform
        if platform in ("tavily", "openblocklabs"):
            raise HTTPException(400, f"LuckMail 渠道暂时不支持 {platform} 项目注册")

        mapping = {
            "trae": "trae",
            "cursor": "cursor",
            "grok": "grok",
            "kiro": "kiro",
            "chatgpt": "openai",
        }
        prepared.extra["luckmail_project_code"] = mapping.get(platform, platform)

    return prepared


def _create_task_record(
    task_id: str, req: RegisterTaskRequest, source: str, meta: dict | None = None
):
    _task_store.create(
        task_id,
        platform=req.platform,
        total=req.count,
        source=source,
        meta=meta,
    )
    _persist_task_snapshot(task_id)


def enqueue_register_task(
    req: RegisterTaskRequest,
    *,
    background_tasks: BackgroundTasks | None = None,
    source: str = "manual",
    meta: dict | None = None,
) -> str:
    prepared = _prepare_register_request(req)
    task_id = f"task_{int(time.time() * 1000)}"
    _create_task_record(task_id, prepared, source, meta)
    if background_tasks is None:
        thread = threading.Thread(
            target=_run_register, args=(task_id, prepared), daemon=True
        )
        thread.start()
    else:
        background_tasks.add_task(_run_register, task_id, prepared)
    return task_id


def has_active_register_task(
    *, platform: str | None = None, source: str | None = None
) -> bool:
    return _task_store.has_active(platform=platform, source=source)


def _log(task_id: str, msg: str):
    """向任务追加一条日志"""
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    _task_store.append_log(task_id, entry)
    _persist_task_snapshot(task_id)
    print(entry)


def _save_task_log(
    platform: str, email: str, status: str, error: str = "", detail: dict = None
):
    """Write a TaskLog record to the database (fire-and-forget, non-blocking)."""
    def _write():
        with Session(engine) as s:
            log = TaskLog(
                platform=platform,
                email=email,
                status=status,
                error=error,
                detail_json=json.dumps(detail or {}, ensure_ascii=False),
            )
            s.add(log)
            s.commit()
    threading.Thread(target=_write, daemon=True).start()


def _auto_upload_integrations(task_id: str, account):
    """注册成功后自动导入外部系统（后台线程，不阻塞注册流程）。"""
    def _run():
        try:
            from services.external_sync import sync_account

            for result in sync_account(account):
                name = result.get("name", "Auto Upload")
                ok = bool(result.get("ok"))
                msg = result.get("msg", "")
                _log(task_id, f"  [{name}] {'[OK] ' + msg if ok else '[FAIL] ' + msg}")
        except Exception as e:
            _log(task_id, f"  [Auto Upload] 自动导入异常: {e}")
    threading.Thread(target=_run, daemon=True).start()


def _run_register(task_id: str, req: RegisterTaskRequest):
    from core.registry import get
    from core.base_platform import RegisterConfig
    from core.db import save_account
    from core.base_mailbox import create_mailbox
    from core.proxy_utils import normalize_proxy_url

    control = _task_store.control_for(task_id)
    _task_store.mark_running(task_id)
    _persist_task_snapshot(task_id)
    success = 0
    skipped = 0
    errors = []
    start_gate_lock = threading.Lock()
    next_start_time = time.time()

    def _sleep_with_control(
        wait_seconds: float,
        *,
        attempt_id: int | None = None,
    ) -> None:
        remaining = max(float(wait_seconds or 0), 0.0)
        while remaining > 0:
            control.checkpoint(attempt_id=attempt_id)
            chunk = min(0.25, remaining)
            time.sleep(chunk)
            remaining -= chunk

    try:
        PlatformCls = get(req.platform)

        # 预先计算 merged_extra，所有线程共享只读副本，避免每线程重复调用 config_store
        from core.config_store import config_store as _cs
        _base_extra = _cs.get_all().copy()
        _base_extra.update(
            {k: v for k, v in req.extra.items() if v is not None and v != ""}
        )

        # 批量预取代理（无固定代理时），减少每线程单独查 DB
        from core.proxy_pool import proxy_pool as _proxy_pool
        _prefetched_proxies: list[str] = []
        _prefetch_lock = threading.Lock()
        if not req.proxy and req.count > 1:
            with Session(engine) as _s:
                from core.db import ProxyModel
                from sqlmodel import select as _sel
                _active = _s.exec(
                    _sel(ProxyModel).where(ProxyModel.is_active == True)
                ).all()
                _prefetched_proxies = [p.url for p in _active if p.url]

        def _get_proxy() -> Optional[str]:
            if req.proxy:
                return req.proxy
            if _prefetched_proxies:
                with _prefetch_lock:
                    if _prefetched_proxies:
                        import random
                        return random.choice(_prefetched_proxies)
            return _proxy_pool.get_next()

        def _build_mailbox(proxy: Optional[str]):
            return create_mailbox(
                provider=_base_extra.get("mail_provider", "luckmail"),
                extra=_base_extra,
                proxy=proxy,
            )

        def _do_one(i: int):
            nonlocal next_start_time
            _proxy = None
            current_email = req.email or ""
            attempt_id: int | None = None
            try:
                control.checkpoint()
                attempt_id = control.start_attempt()
                control.checkpoint(attempt_id=attempt_id)
                _proxy = normalize_proxy_url(_get_proxy())
                if req.register_delay_seconds > 0:
                    with start_gate_lock:
                        control.checkpoint(attempt_id=attempt_id)
                        now = time.time()
                        wait_seconds = max(0.0, next_start_time - now)
                        if wait_seconds > 0:
                            _log(
                                task_id,
                                f"第 {i + 1} 个账号启动前延迟 {wait_seconds:g} 秒",
                            )
                            _sleep_with_control(
                                wait_seconds,
                                attempt_id=attempt_id,
                            )
                        next_start_time = time.time() + req.register_delay_seconds
                control.checkpoint(attempt_id=attempt_id)

                merged_extra = _base_extra

                _config = RegisterConfig(
                    executor_type=req.executor_type,
                    captcha_solver=req.captcha_solver,
                    proxy=_proxy,
                    extra=merged_extra,
                )
                _mailbox = _build_mailbox(_proxy)
                _platform = PlatformCls(config=_config, mailbox=_mailbox)
                _platform._task_attempt_token = attempt_id
                _platform._log_fn = lambda msg: _log(task_id, msg)
                _platform.bind_task_control(control)
                if getattr(_platform, "mailbox", None) is not None:
                    _platform.mailbox._task_attempt_token = attempt_id
                    _platform.mailbox._log_fn = _platform._log_fn
                _task_store.set_progress(task_id, f"{i + 1}/{req.count}")
                _persist_task_snapshot(task_id)
                _log(task_id, f"开始注册第 {i + 1}/{req.count} 个账号")
                if _proxy:
                    _log(task_id, f"使用代理: {_proxy}")
                account = _platform.register(
                    email=req.email or None,
                    password=req.password,
                )
                current_email = account.email or current_email
                if str(merged_extra.get("mail_provider", "")).strip() == "cfworker":
                    from core.email_domain_policy import validate_email_domain_policy

                    validate_email_domain_policy(
                        account.email,
                        {
                            "email_domain_rule_enabled": merged_extra.get(
                                "email_domain_rule_enabled", "0"
                            ),
                            "email_domain_level_count": merged_extra.get(
                                "email_domain_level_count", "2"
                            ),
                        },
                    )
                if isinstance(account.extra, dict):
                    mail_provider = merged_extra.get("mail_provider", "")
                    if mail_provider:
                        account.extra.setdefault("mail_provider", mail_provider)
                    if mail_provider == "luckmail" and req.platform == "chatgpt":
                        mailbox_token = getattr(_mailbox, "_token", "") or ""
                        if mailbox_token:
                            account.extra.setdefault("mailbox_token", mailbox_token)
                        if merged_extra.get("luckmail_project_code"):
                            account.extra.setdefault(
                                "luckmail_project_code",
                                merged_extra.get("luckmail_project_code"),
                            )
                        if merged_extra.get("luckmail_email_type"):
                            account.extra.setdefault(
                                "luckmail_email_type",
                                merged_extra.get("luckmail_email_type"),
                            )
                        if merged_extra.get("luckmail_domain"):
                            account.extra.setdefault(
                                "luckmail_domain", merged_extra.get("luckmail_domain")
                            )
                        if merged_extra.get("luckmail_base_url"):
                            account.extra.setdefault(
                                "luckmail_base_url",
                                merged_extra.get("luckmail_base_url"),
                            )
                saved_account = save_account(account)
                if _proxy:
                    _proxy_pool.report_success(_proxy)
                _log(task_id, f"[OK] 注册成功: {account.email}")
                _save_task_log(req.platform, account.email, "success")
                _auto_upload_integrations(task_id, saved_account or account)
                cashier_url = (account.extra or {}).get("cashier_url", "")
                if cashier_url:
                    _log(task_id, f"  [升级链接] {cashier_url}")
                    _task_store.add_cashier_url(task_id, cashier_url)
                    _persist_task_snapshot(task_id)
                return AttemptResult.success()
            except SkipCurrentAttemptRequested as e:
                _log(task_id, f"[SKIP] 已跳过当前账号: {e}")
                _save_task_log(
                    req.platform,
                    current_email,
                    "skipped",
                    error=str(e),
                )
                return AttemptResult.skipped(str(e))
            except StopTaskRequested as e:
                _log(task_id, f"[STOP] {e}")
                return AttemptResult.stopped(str(e))
            except Exception as e:
                if _proxy:
                    _proxy_pool.report_fail(_proxy)
                _log(task_id, f"[FAIL] 注册失败: {e}")
                _save_task_log(
                    req.platform,
                    current_email,
                    "failed",
                    error=str(e),
                )
                return AttemptResult.failed(str(e))
            finally:
                control.finish_attempt(attempt_id)

        from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed

        max_workers = min(req.concurrency, req.count)
        stopped = False
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_do_one, i) for i in range(req.count)]
            for f in as_completed(futures):
                try:
                    result = f.result()
                except CancelledError:
                    continue
                except Exception as e:
                    _log(task_id, f"[ERROR] 任务线程异常: {e}")
                    errors.append(str(e))
                    continue
                if result.outcome == AttemptOutcome.SUCCESS:
                    success += 1
                elif result.outcome == AttemptOutcome.SKIPPED:
                    skipped += 1
                elif result.outcome == AttemptOutcome.STOPPED:
                    stopped = True
                else:
                    errors.append(result.message)
                _task_store.update_counters(
                    task_id,
                    success=success,
                    registered=success + skipped + len(errors),
                )
                _persist_task_snapshot(task_id)
                if stopped or control.is_stop_requested():
                    stopped = True
                    for pending in futures:
                        if pending is not f:
                            pending.cancel()
    except Exception as e:
        _log(task_id, f"致命错误: {e}")
        _task_store.finish(
            task_id,
            status="failed",
            success=success,
            registered=success + skipped + len(errors),
            skipped=skipped,
            errors=errors,
            error=str(e),
        )
        _persist_task_snapshot(task_id)
        _task_store.cleanup()
        return

    final_status = "stopped" if control.is_stop_requested() or stopped else "done"
    if final_status == "stopped":
        summary = (
            f"任务已停止: 成功 {success} 个, 跳过 {skipped} 个, 失败 {len(errors)} 个"
        )
    else:
        summary = f"完成: 成功 {success} 个, 跳过 {skipped} 个, 失败 {len(errors)} 个"
    _log(task_id, summary)
    _task_store.finish(
        task_id,
        status=final_status,
        success=success,
        registered=success + skipped + len(errors),
        skipped=skipped,
        errors=errors,
    )
    _persist_task_snapshot(task_id)
    _task_store.cleanup()


@router.post("/register")
def create_register_task(
    req: RegisterTaskRequest,
    background_tasks: BackgroundTasks,
):
    task_id = enqueue_register_task(req, background_tasks=background_tasks)
    return {"task_id": task_id}


@router.post("/{task_id}/skip-current")
def skip_current_account(task_id: str):
    _finalize_orphan_tasks()
    _ensure_task_mutable(task_id)
    if not _task_store.exists(task_id):
        raise HTTPException(409, "任务已结束或服务已重启，无法跳过当前账号")
    control = _task_store.request_skip_current(task_id)
    _log(task_id, "收到手动跳过当前账号请求")
    return {"ok": True, "task_id": task_id, "control": control}


@router.post("/{task_id}/stop")
def stop_task(task_id: str):
    _finalize_orphan_tasks()
    _ensure_task_mutable(task_id)
    if not _task_store.exists(task_id):
        raise HTTPException(409, "任务已结束或服务已重启，无法停止")
    control = _task_store.request_stop(task_id)
    _log(task_id, "收到手动停止任务请求")
    return {"ok": True, "task_id": task_id, "control": control}


@router.get("/logs")
def get_logs(platform: str = None, page: int = 1, page_size: int = 50):
    with Session(engine) as s:
        q = select(TaskLog)
        if platform:
            q = q.where(TaskLog.platform == platform)
        q = q.order_by(TaskLog.id.desc())
        total = len(s.exec(q).all())
        items = s.exec(q.offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": items}


@router.post("/logs/batch-delete")
def batch_delete_logs(body: TaskLogBatchDeleteRequest):
    if not body.ids:
        raise HTTPException(400, "任务历史 ID 列表不能为空")

    unique_ids = list(dict.fromkeys(body.ids))
    if len(unique_ids) > 1000:
        raise HTTPException(400, "单次最多删除 1000 条任务历史")

    with Session(engine) as s:
        try:
            logs = s.exec(select(TaskLog).where(TaskLog.id.in_(unique_ids))).all()
            found_ids = {log.id for log in logs if log.id is not None}

            for log in logs:
                s.delete(log)

            s.commit()
            deleted_count = len(found_ids)
            not_found_ids = [log_id for log_id in unique_ids if log_id not in found_ids]
            logger.info("批量删除任务历史成功: %s 条", deleted_count)

            return {
                "deleted": deleted_count,
                "not_found": not_found_ids,
                "total_requested": len(unique_ids),
            }
        except Exception as e:
            s.rollback()
            logger.exception("批量删除任务历史失败")
            raise HTTPException(500, f"批量删除任务历史失败: {str(e)}")


@router.get("/{task_id}/logs/stream")
async def stream_logs(task_id: str, since: int = 0):
    """SSE 实时日志流"""
    _finalize_orphan_tasks()
    _ensure_task_exists(task_id)

    async def event_generator():
        sent = since
        use_memory = _task_store.exists(task_id)
        while True:
            if use_memory:
                logs, status = _task_store.log_state(task_id)
                snapshot = _task_store.snapshot(task_id)
                _persist_task_snapshot(task_id)
            else:
                snapshot = _get_persisted_task(task_id) or {}
                logs = snapshot.get("logs") or []
                status = snapshot.get("status") or "failed"
            counters = {
                "success": int(snapshot.get("success") or 0),
                "registered": int(snapshot.get("registered") or 0),
                "total": int(snapshot.get("total") or 0),
            }
            while sent < len(logs):
                yield f"data: {json.dumps({'line': logs[sent], **counters})}\n\n"
                sent += 1
            if status in ("done", "failed", "stopped"):
                yield f"data: {json.dumps({'done': True, 'status': status, **counters})}\n\n"
                break
            if not use_memory:
                # 非内存任务仅提供持久化快照，不进入无限轮询
                yield f"data: {json.dumps({'done': True, 'status': 'stopped', **counters})}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{task_id}")
def get_task(task_id: str):
    _finalize_orphan_tasks()
    return _get_task_snapshot(task_id)


@router.get("")
def list_tasks():
    _finalize_orphan_tasks()
    # 以 DB 为主返回，避免进程重启导致列表丢失
    return _list_persisted_tasks()


@router.delete("/{task_id}")
def delete_task(task_id: str):
    _finalize_orphan_tasks()
    snapshot = _get_task_snapshot(task_id)
    status = str(snapshot.get("status") or "")
    if status in {"pending", "running"}:
        raise HTTPException(409, "运行中的任务不允许删除，请先停止任务")
    with Session(engine) as s:
        row = s.get(TaskRunModel, task_id)
        if row is not None:
            s.delete(row)
            s.commit()
    return {"ok": True, "task_id": task_id}
