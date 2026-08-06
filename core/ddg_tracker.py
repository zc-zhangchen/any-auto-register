"""DuckDuckGo Key 每日用量追踪器。

使用 SQLite 记录每个 Key 每天生成了多少个邮箱别名，
自动选择当天未达限额的 Key。
"""

import json
import time
import threading
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Session, select, func, col
from .db import engine


class DdgUsage(SQLModel, table=True):
    """DDG 邮箱生成记录"""

    __tablename__ = "ddg_usage"

    id: Optional[int] = Field(default=None, primary_key=True)
    key_index: int = Field(index=True)
    date: str = Field(index=True)  # YYYY-MM-DD
    email: str = ""
    created_at: float = Field(default_factory=time.time)


class DdgUsageTracker:
    """线程安全的 DDG Key 用量追踪器。"""

    DEFAULT_DAILY_LIMIT = 50

    def __init__(self, daily_limit: int = 50):
        self.daily_limit = max(int(daily_limit or self.DEFAULT_DAILY_LIMIT), 1)
        self._lock = threading.Lock()
        # 确保表存在
        SQLModel.metadata.create_all(engine, tables=[DdgUsage.__table__])

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def record_usage(self, key_index: int, email: str = "") -> None:
        """记录某个 Key 的一次使用。"""
        with self._lock:
            with Session(engine) as s:
                record = DdgUsage(
                    key_index=key_index,
                    date=self._today(),
                    email=email,
                )
                s.add(record)
                s.commit()

    def get_daily_usage(self, key_index: int, date: str = "") -> int:
        """获取某 Key 在指定日期的用量（默认今天）。"""
        target_date = date or self._today()
        with Session(engine) as s:
            count = s.exec(
                select(func.count(col(DdgUsage.id))).where(
                    DdgUsage.key_index == key_index,
                    DdgUsage.date == target_date,
                )
            ).one()
            return int(count or 0)

    def get_available_key_index(self, total_keys: int) -> int:
        """
        基于轮询（round-robin）策略返回下一个当天用量 < daily_limit 的 Key 索引。
        从上次使用的 Key 的下一个开始查找，实现多 Key 均匀分配。
        如果所有 Key 都已达限额，抛出 RuntimeError。
        """
        today = self._today()
        with Session(engine) as s:
            # 查找今天最新一次使用的 key_index，作为轮询起点
            latest = s.exec(
                select(col(DdgUsage.key_index))
                .where(DdgUsage.date == today)
                .order_by(col(DdgUsage.created_at).desc())
                .limit(1)
            ).first()
            start = (latest + 1) % total_keys if latest is not None else 0

            for i in range(total_keys):
                idx = (start + i) % total_keys
                count = s.exec(
                    select(func.count(col(DdgUsage.id))).where(
                        DdgUsage.key_index == idx,
                        DdgUsage.date == today,
                    )
                ).one()
                if int(count or 0) < self.daily_limit:
                    return idx

        raise RuntimeError(
            f"所有 DDG Key ({total_keys} 个) 今日已达限额 ({self.daily_limit}/Key)，"
            f"请明天再试或添加更多 Key"
        )

    def get_all_status(self, total_keys: int) -> list[dict]:
        """返回所有 Key 的用量状态。"""
        today = self._today()
        result = []
        with Session(engine) as s:
            for idx in range(total_keys):
                count = s.exec(
                    select(func.count(col(DdgUsage.id))).where(
                        DdgUsage.key_index == idx,
                        DdgUsage.date == today,
                    )
                ).one()
                usage = int(count or 0)
                result.append(
                    {
                        "key_index": idx,
                        "date": today,
                        "usage": usage,
                        "limit": self.daily_limit,
                        "available": usage < self.daily_limit,
                    }
                )
        return result
