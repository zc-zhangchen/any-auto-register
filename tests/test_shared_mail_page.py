"""隐私邮箱最新邮件的免登录页面。

重点是两件事：链接不带 token 猜不出来，以及面板设了密码时这个页面依然打得开
——它存在的意义就是复制给不登录面板的人看。
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from platforms.icloud.models import MailAddress, MailMessage


def _message(subject: str, html_body: str = "", text_body: str = "") -> MailMessage:
    return MailMessage(
        provider_message_id="uid-1",
        mailbox="INBOX",
        subject=subject,
        snippet="片段",
        text_body=text_body,
        html_body=html_body,
        sender=MailAddress(email="noreply@tm.openai.com", name="OpenAI"),
        to=[MailAddress(email="alias@icloud.com")],
        received_at=datetime(2026, 8, 21, 5, 20, tzinfo=timezone.utc),
    )


@pytest.fixture
def shared(tmp_path, monkeypatch):
    import core.config_store as config_store_module
    import core.db as db
    from core.db import ICloudAccountModel, ICloudAliasModel
    from services import icloud_service

    engine = create_engine(f"sqlite:///{tmp_path / 'shared.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(config_store_module, "engine", engine)
    monkeypatch.setattr(icloud_service, "engine", engine)

    with Session(engine) as session:
        account = ICloudAccountModel(email="owner@icloud.com")
        session.add(account)
        session.commit()
        session.refresh(account)
        alias = ICloudAliasModel(account_id=account.id, address="alias@icloud.com")
        session.add(alias)
        session.commit()
        session.refresh(alias)
        token = alias.share_token

    inbox: list[MailMessage] = []
    monkeypatch.setattr(
        icloud_service,
        "fetch_account_messages",
        lambda *_args, **_kwargs: list(inbox),
    )

    from main import app

    client = TestClient(app)
    return client, token, inbox


def test_alias_rows_get_an_unguessable_token(shared):
    _client, token, _inbox = shared

    assert len(token) >= 20
    assert not token.isdigit()


def test_page_shows_the_newest_message_without_any_login(shared):
    client, token, inbox = shared
    inbox.extend(
        [
            _message("最新一封：验证码 481203", html_body="<p>code <b>481203</b></p>"),
            _message("上一封"),
        ]
    )

    response = client.get(f"/m/{token}")

    assert response.status_code == 200
    assert "Authorization" not in response.request.headers
    body = response.text
    assert "最新一封：验证码 481203" in body
    assert "上一封" not in body
    assert "alias@icloud.com" in body
    assert response.headers["cache-control"] == "no-store"


def test_page_stays_open_when_the_panel_has_a_password(shared):
    """面板设了密码，/api 全都 401，但这条链接照样能打开。"""
    client, token, inbox = shared
    inbox.append(_message("验证码"))

    from core.config_store import config_store

    config_store.set("auth_password_hash", "not-a-real-hash")

    assert client.get("/api/icloud/aliases").status_code == 401
    assert client.get(f"/m/{token}").status_code == 200


def test_untrusted_mail_html_cannot_execute(shared):
    client, token, inbox = shared
    inbox.append(_message("危险邮件", html_body="<script>alert(1)</script><p>hi</p>"))

    body = client.get(f"/m/{token}").text

    # 正文只以转义后的形式出现在 srcdoc 属性里，页面本身不会多出一个可执行的 script
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert 'sandbox="allow-same-origin"' in body


def test_plain_text_mail_renders_too(shared):
    client, token, inbox = shared
    inbox.append(_message("纯文本", text_body="验证码 998877"))

    body = client.get(f"/m/{token}").text

    assert "验证码 998877" in body


def test_empty_inbox_says_so_instead_of_erroring(shared):
    client, token, _inbox = shared

    response = client.get(f"/m/{token}")

    assert response.status_code == 200
    assert "还没有邮件" in response.text


def test_unknown_token_is_a_404_page(shared):
    client, _token, _inbox = shared

    response = client.get("/m/definitely-not-a-real-token")

    assert response.status_code == 404
    assert "链接无效" in response.text


def test_migration_backfills_tokens_for_older_rows(tmp_path, monkeypatch):
    import core.db as db
    from core.db import ICloudAccountModel, ICloudAliasModel, init_db

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(db, "engine", engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        account = ICloudAccountModel(email="owner@icloud.com")
        session.add(account)
        session.commit()
        session.refresh(account)
        for address in ("a@icloud.com", "b@icloud.com"):
            session.add(
                ICloudAliasModel(account_id=account.id, address=address, share_token="")
            )
        session.commit()

    init_db()

    with Session(engine) as session:
        tokens = [row.share_token for row in session.exec(select(ICloudAliasModel)).all()]
    assert all(tokens)
    assert len(set(tokens)) == 2
