"""数据库模型 - SQLite via SQLModel"""
from datetime import datetime, timezone
import os
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session, select
import json


def _utcnow():
    return datetime.now(timezone.utc)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///account_manager.db")
engine = create_engine(DATABASE_URL)


class AccountModel(SQLModel, table=True):
    __tablename__ = "accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(index=True)
    email: str = Field(index=True)
    password: str
    user_id: str = ""
    region: str = ""
    token: str = ""
    status: str = "registered"
    trial_end_time: int = 0
    cashier_url: str = ""
    extra_json: str = "{}"   # JSON 存储平台自定义字段
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def get_extra(self) -> dict:
        return json.loads(self.extra_json or "{}")

    def set_extra(self, d: dict):
        self.extra_json = json.dumps(d, ensure_ascii=False)


class TaskLog(SQLModel, table=True):
    __tablename__ = "task_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str
    email: str
    status: str        # success | failed
    error: str = ""
    detail_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


class TaskRunModel(SQLModel, table=True):
    __tablename__ = "task_runs"

    id: str = Field(primary_key=True)
    platform: str = Field(index=True)
    source: str = Field(default="manual", index=True)
    status: str = Field(default="pending", index=True)
    total: int = 0
    progress: str = "0/0"
    success: int = 0
    registered: int = 0
    skipped: int = 0
    error: str = ""
    meta_json: str = "{}"
    logs_json: str = "[]"
    errors_json: str = "[]"
    cashier_urls_json: str = "[]"
    control_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class OutlookAccountModel(SQLModel, table=True):
    __tablename__ = "outlook_accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, sa_column_kwargs={"unique": True})
    password: str
    client_id: str = ""
    refresh_token: str = ""
    account_type: str = "microsoft_oauth"
    mailapi_url: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    last_used: Optional[datetime] = None


class ProxyModel(SQLModel, table=True):
    __tablename__ = "proxies"

    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(unique=True)
    region: str = ""
    success_count: int = 0
    fail_count: int = 0
    is_active: bool = True
    last_checked: Optional[datetime] = None


def save_account(account) -> 'AccountModel':
    """从 base_platform.Account 存入数据库（同平台同邮箱则更新）"""
    with Session(engine) as session:
        existing = session.exec(
            select(AccountModel)
            .where(AccountModel.platform == account.platform)
            .where(AccountModel.email == account.email)
        ).first()
        if existing:
            existing.password = account.password
            existing.user_id = account.user_id or ""
            existing.region = account.region or ""
            existing.token = account.token or ""
            existing.status = account.status.value
            existing.extra_json = json.dumps(account.extra or {}, ensure_ascii=False)
            existing.cashier_url = (account.extra or {}).get("cashier_url", "")
            existing.updated_at = _utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        m = AccountModel(
            platform=account.platform,
            email=account.email,
            password=account.password,
            user_id=account.user_id or "",
            region=account.region or "",
            token=account.token or "",
            status=account.status.value,
            extra_json=json.dumps(account.extra or {}, ensure_ascii=False),
            cashier_url=(account.extra or {}).get("cashier_url", ""),
        )
        session.add(m)
        session.commit()
        session.refresh(m)
        return m


def _migrate_outlook_accounts_schema() -> None:
    if engine.url.get_backend_name() != "sqlite":
        return
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info('outlook_accounts')").fetchall()
        if not rows:
            return
        existing_columns = {str(row[1]) for row in rows}
        if "account_type" not in existing_columns:
            conn.exec_driver_sql(
                "ALTER TABLE outlook_accounts ADD COLUMN account_type TEXT DEFAULT 'microsoft_oauth'"
            )
        if "mailapi_url" not in existing_columns:
            conn.exec_driver_sql(
                "ALTER TABLE outlook_accounts ADD COLUMN mailapi_url TEXT DEFAULT ''"
            )
        conn.exec_driver_sql(
            "UPDATE outlook_accounts SET account_type = 'microsoft_oauth' WHERE account_type IS NULL OR TRIM(account_type) = ''"
        )
        conn.exec_driver_sql(
            "UPDATE outlook_accounts SET mailapi_url = '' WHERE mailapi_url IS NULL"
        )


def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate_outlook_accounts_schema()


def get_session():
    with Session(engine) as session:
        yield session
