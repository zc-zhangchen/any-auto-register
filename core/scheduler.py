"""定时任务调度 - 账号有效性检测、trial 到期提醒"""
from datetime import datetime, timezone
from sqlmodel import Session, select
from .db import engine, AccountModel
from .registry import get, load_all
from .base_platform import Account, AccountStatus, RegisterConfig
import threading
import time


class Scheduler:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread = None
        self._loop_interval_seconds = 60
        self._trial_check_interval_seconds = 3600
        self._last_trial_check_at = 0.0
        self._last_cpa_maintenance_at = 0.0

    def start(self):
        if self._running:
            return
        self._running = True
        self._last_trial_check_at = 0.0
        self._last_cpa_maintenance_at = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Scheduler] 已启动")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            now = time.time()
            if now - self._last_trial_check_at >= self._trial_check_interval_seconds:
                try:
                    self.check_trial_expiry()
                    self._last_trial_check_at = now
                except Exception as e:
                    print(f"[Scheduler] Trial 检查错误: {e}")

            cpa_interval = self._get_cpa_maintenance_interval_seconds()
            if cpa_interval and now - self._last_cpa_maintenance_at >= cpa_interval:
                try:
                    self.check_cpa_credentials()
                    self._last_cpa_maintenance_at = now
                except Exception as e:
                    print(f"[Scheduler] CPA 维护错误: {e}")

            time.sleep(self._loop_interval_seconds)

    def _get_cpa_maintenance_interval_seconds(self) -> int:
        from services.cpa_manager import get_cpa_maintenance_interval_seconds

        return get_cpa_maintenance_interval_seconds()

    def check_trial_expiry(self):
        """检查 trial 到期账号，更新状态"""
        now = int(datetime.now(timezone.utc).timestamp())
        with Session(engine) as s:
            accounts = s.exec(
                select(AccountModel).where(AccountModel.status == "trial")
            ).all()
            updated = 0
            for acc in accounts:
                if acc.trial_end_time and acc.trial_end_time < now:
                    acc.status = AccountStatus.EXPIRED.value
                    acc.updated_at = datetime.now(timezone.utc)
                    s.add(acc)
                    updated += 1
            s.commit()
            if updated:
                print(f"[Scheduler] {updated} 个 trial 账号已到期")

    def check_accounts_valid(self, platform: str = None, limit: int = 50):
        """批量检测账号有效性"""
        load_all()
        with Session(engine) as s:
            q = select(AccountModel).where(
                AccountModel.status.in_(["registered", "trial", "subscribed"])
            )
            if platform:
                q = q.where(AccountModel.platform == platform)
            accounts = s.exec(q.limit(limit)).all()

        results = {"valid": 0, "invalid": 0, "error": 0}
        for acc in accounts:
            try:
                PlatformCls = get(acc.platform)
                plugin = PlatformCls(config=RegisterConfig())
                import json
                account_obj = Account(
                    platform=acc.platform,
                    email=acc.email,
                    password=acc.password,
                    user_id=acc.user_id,
                    region=acc.region,
                    token=acc.token,
                    extra=json.loads(acc.extra_json or "{}"),
                )
                valid = plugin.check_valid(account_obj)
                with Session(engine) as s:
                    a = s.get(AccountModel, acc.id)
                    if a:
                        if acc.platform != "chatgpt":
                            a.status = acc.status if valid else AccountStatus.INVALID.value
                        a.updated_at = datetime.now(timezone.utc)
                        s.add(a)
                        s.commit()
                if valid:
                    results["valid"] += 1
                else:
                    results["invalid"] += 1
            except Exception:
                results["error"] += 1
        return results

    def check_cpa_credentials(self):
        """清理 CPA 中的 error 凭证，并在低于阈值时自动补注册。"""
        from services.cpa_manager import maintain_cpa_credentials

        return maintain_cpa_credentials()


scheduler = Scheduler()
