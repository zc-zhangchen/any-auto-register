from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MailImportProviderType = Literal["applemail", "microsoft"]
MailRecoveryPoolMailboxFilter = Literal["all", "outlook", "hotmail"]
MailRecoveryPoolMailboxType = Literal["outlook", "hotmail", "other"]
MailRecoveryPoolStatusFilter = Literal["all", "leased", "recoverable"]

DEFAULT_PREVIEW_LIMIT = 100
MAX_PREVIEW_LIMIT = 500


class MailImportProviderDescriptor(BaseModel):
    type: MailImportProviderType
    label: str
    description: str
    content_placeholder: str
    helper_text: str = ""
    supports_filename: bool = False
    filename_label: str = ""
    filename_placeholder: str = ""
    preview_empty_text: str = ""


class MailImportSnapshotItem(BaseModel):
    index: int
    email: str
    mailbox: str = ""
    enabled: bool | None = None
    has_oauth: bool | None = None


class MailImportSnapshotRequest(BaseModel):
    type: MailImportProviderType
    pool_dir: str = ""
    pool_file: str = ""
    preview_limit: int = Field(
        default=DEFAULT_PREVIEW_LIMIT,
        ge=1,
        le=MAX_PREVIEW_LIMIT,
    )


class MailImportExecuteRequest(BaseModel):
    type: MailImportProviderType
    content: str
    filename: str = ""
    pool_dir: str = ""
    pool_file: str = ""
    enabled: bool = True
    bind_to_config: bool = True
    preview_limit: int = Field(
        default=DEFAULT_PREVIEW_LIMIT,
        ge=1,
        le=MAX_PREVIEW_LIMIT,
    )


class MailImportDeleteRequest(BaseModel):
    type: MailImportProviderType
    email: str
    mailbox: str = ""
    pool_dir: str = ""
    pool_file: str = ""
    preview_limit: int = Field(
        default=DEFAULT_PREVIEW_LIMIT,
        ge=1,
        le=MAX_PREVIEW_LIMIT,
    )


class MailImportDeleteItem(BaseModel):
    email: str
    mailbox: str = ""


class MailImportBatchDeleteRequest(BaseModel):
    type: MailImportProviderType
    items: list[MailImportDeleteItem] = Field(default_factory=list)
    pool_dir: str = ""
    pool_file: str = ""
    preview_limit: int = Field(
        default=DEFAULT_PREVIEW_LIMIT,
        ge=1,
        le=MAX_PREVIEW_LIMIT,
    )


class MailImportSnapshot(BaseModel):
    type: MailImportProviderType
    label: str
    count: int
    items: list[MailImportSnapshotItem] = Field(default_factory=list)
    truncated: bool = False
    filename: str = ""
    path: str = ""
    pool_dir: str = ""


class MailImportSummary(BaseModel):
    total: int
    success: int
    failed: int


class MailImportResponse(BaseModel):
    type: MailImportProviderType
    summary: MailImportSummary
    snapshot: MailImportSnapshot
    errors: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class MailRecoveryPoolRequest(BaseModel):
    mailbox_type: MailRecoveryPoolMailboxFilter = "all"
    status: MailRecoveryPoolStatusFilter = "all"
    search: str = ""
    limit: int = Field(
        default=DEFAULT_PREVIEW_LIMIT,
        ge=1,
        le=MAX_PREVIEW_LIMIT,
    )


class MailRecoveryPoolItem(BaseModel):
    id: int
    email: str
    mailbox_type: MailRecoveryPoolMailboxType
    status: str
    has_oauth: bool = False
    source_account_id: int | None = None
    task_attempt_id: str = ""
    last_error: str = ""
    leased_at: datetime | None = None
    last_failed_at: datetime | None = None
    updated_at: datetime | None = None


class MailRecoveryPoolSummary(BaseModel):
    total: int = 0
    leased: int = 0
    recoverable: int = 0
    hotmail: int = 0
    outlook: int = 0
    other: int = 0


class MailRecoveryPoolResponse(BaseModel):
    mailbox_type: MailRecoveryPoolMailboxFilter
    status: MailRecoveryPoolStatusFilter
    search: str = ""
    count: int
    items: list[MailRecoveryPoolItem] = Field(default_factory=list)
    truncated: bool = False
    summary: MailRecoveryPoolSummary = Field(default_factory=MailRecoveryPoolSummary)


class MailRecoveryPoolRestoreRequest(BaseModel):
    id: int = Field(ge=1)
