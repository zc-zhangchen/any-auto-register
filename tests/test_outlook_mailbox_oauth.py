import unittest
from unittest import mock

from sqlmodel import Session, SQLModel, create_engine, select

from core.base_mailbox import MailboxAccount, OutlookMailbox, create_mailbox
from core.db import OutlookAccountLeaseModel, OutlookAccountModel


class _FakeResponse:
    def __init__(self, status_code, payload=None, text="", json_error=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or ""
        self.content = b"{}" if payload is not None or json_error is not None else b""
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return dict(self._payload)


class OutlookMailboxOAuthTests(unittest.TestCase):
    def test_create_mailbox_outlook_defaults_to_graph_backend(self):
        mailbox = create_mailbox("outlook", extra={})

        self.assertIsInstance(mailbox, OutlookMailbox)
        self.assertEqual(mailbox._backend_name, "graph")

    @mock.patch("requests.post")
    def test_fetch_oauth_token_graph_backend_prefers_graph_scope(self, mock_post):
        mailbox = OutlookMailbox(token_endpoint="https://token.example.test")

        responses = [
            _FakeResponse(
                400,
                text='{"error":"invalid_grant","error_description":"scopes requested are unauthorized"}',
            ),
            _FakeResponse(
                200,
                payload={"access_token": "access-token-demo"},
                text='{"access_token":"access-token-demo"}',
            ),
        ]
        mock_post.side_effect = responses

        token = mailbox._fetch_oauth_token(
            email="demo@outlook.com",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        self.assertEqual(token, "access-token-demo")
        self.assertEqual(mock_post.call_count, 2)

        first_scope = mock_post.call_args_list[0].kwargs["data"].get("scope", "")
        second_scope = mock_post.call_args_list[1].kwargs["data"].get("scope", "")
        self.assertEqual(
            first_scope,
            "https://graph.microsoft.com/.default",
        )
        self.assertEqual(
            second_scope,
            "https://outlook.office.com/.default offline_access",
        )

    @mock.patch("requests.post")
    def test_fetch_oauth_token_imap_backend_prefers_imap_scope(self, mock_post):
        mailbox = OutlookMailbox(
            token_endpoint="https://token.example.test",
            backend="imap",
        )
        mock_post.side_effect = [
            _FakeResponse(
                200,
                payload={"access_token": "imap-token"},
                text='{"access_token":"imap-token"}',
            ),
        ]

        token = mailbox._fetch_oauth_token(
            email="demo@outlook.com",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        self.assertEqual(token, "imap-token")
        self.assertEqual(
            mock_post.call_args.kwargs["data"].get("scope", ""),
            "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
        )

    @mock.patch("requests.post")
    def test_probe_oauth_availability_detects_service_abuse_mode(self, mock_post):
        mailbox = OutlookMailbox(token_endpoint="https://token.example.test")
        mock_post.return_value = _FakeResponse(
            400,
            text='{"error":"invalid_grant","error_description":"User account is found to be in service abuse mode."}',
        )

        result = mailbox.probe_oauth_availability(
            email="demo@hotmail.com",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "service_abuse_mode")
        self.assertIn("service abuse mode", result["message"])

    @mock.patch("requests.post")
    def test_probe_oauth_availability_returns_ok_when_access_token_is_obtained(self, mock_post):
        mailbox = OutlookMailbox(token_endpoint="https://token.example.test")
        mock_post.return_value = _FakeResponse(
            200,
            payload={"access_token": "ok-token", "expires_in": 3600},
            text='{"access_token":"ok-token","expires_in":3600}',
        )

        result = mailbox.probe_oauth_availability(
            email="demo@outlook.com",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "ok")
        self.assertEqual(result["access_token"], "ok-token")

    @mock.patch("requests.post")
    @mock.patch("requests.request")
    def test_wait_for_code_uses_graph_backend_by_default(self, mock_request, mock_post):
        mailbox = OutlookMailbox(token_endpoint="https://token.example.test")
        account = MailboxAccount(
            email="demo@outlook.com",
            extra={
                "client_id": "client-id",
                "refresh_token": "refresh-token",
            },
        )
        mock_post.return_value = _FakeResponse(
            200,
            payload={"access_token": "graph-token", "expires_in": 3600},
            text='{"access_token":"graph-token","expires_in":3600}',
        )
        mock_request.return_value = _FakeResponse(
            200,
            payload={
                "value": [
                    {
                        "id": "message-1",
                        "subject": "OpenAI verification code",
                        "bodyPreview": "Your verification code is 123456",
                    }
                ]
            },
        )

        code = mailbox.wait_for_code(account, timeout=5)

        self.assertEqual(code, "123456")
        self.assertIn(
            "/me/mailFolders/inbox/messages",
            str(mock_request.call_args.args[1]),
        )

    @mock.patch("requests.post")
    @mock.patch("requests.request")
    def test_wait_for_code_reads_deleteditems_folder_when_inbox_has_no_new_code(self, mock_request, mock_post):
        mailbox = OutlookMailbox(token_endpoint="https://token.example.test")
        account = MailboxAccount(
            email="demo@outlook.com",
            extra={
                "client_id": "client-id",
                "refresh_token": "refresh-token",
            },
        )
        mock_post.return_value = _FakeResponse(
            200,
            payload={"access_token": "graph-token", "expires_in": 3600},
            text='{"access_token":"graph-token","expires_in":3600}',
        )
        mock_request.side_effect = [
            _FakeResponse(200, payload={"value": []}),
            _FakeResponse(200, payload={"value": []}),
            _FakeResponse(
                200,
                payload={
                    "value": [
                        {
                            "id": "deleted-message-1",
                            "subject": "OpenAI verification code",
                            "bodyPreview": "Your verification code is 654321",
                        }
                    ]
                },
            ),
        ]

        code = mailbox.wait_for_code(account, timeout=5)

        self.assertEqual(code, "654321")
        requested_urls = [str(call.args[1]) for call in mock_request.call_args_list]
        self.assertTrue(any("/me/mailFolders/deleteditems/messages" in url for url in requested_urls))

    @mock.patch("requests.post")
    @mock.patch("requests.request")
    def test_wait_for_code_skips_graph_messages_older_than_otp_sent_at(self, mock_request, mock_post):
        mailbox = OutlookMailbox(token_endpoint="https://token.example.test")
        mailbox._graph_folder_names = ["inbox"]
        account = MailboxAccount(
            email="demo@outlook.com",
            extra={
                "client_id": "client-id",
                "refresh_token": "refresh-token",
            },
        )
        mock_post.return_value = _FakeResponse(
            200,
            payload={"access_token": "graph-token", "expires_in": 3600},
            text='{"access_token":"graph-token","expires_in":3600}',
        )
        mock_request.side_effect = [
            _FakeResponse(
                200,
                payload={
                    "value": [
                        {
                            "id": "message-old",
                            "subject": "OpenAI verification code",
                            "bodyPreview": "Your verification code is 111111",
                            "receivedDateTime": "1970-01-01T00:01:00+00:00",
                        }
                    ]
                },
            ),
            _FakeResponse(
                200,
                payload={
                    "value": [
                        {
                            "id": "message-new",
                            "subject": "OpenAI verification code",
                            "bodyPreview": "Your verification code is 222222",
                            "receivedDateTime": "1970-01-01T00:05:00+00:00",
                        }
                    ]
                },
            ),
        ]

        def run_two_polls(*, poll_once, **kwargs):
            first = poll_once()
            if first:
                return first
            second = poll_once()
            if second:
                return second
            raise TimeoutError("expected a fresh OTP")

        with mock.patch.object(mailbox, "_run_polling_wait", side_effect=run_two_polls):
            code = mailbox.wait_for_code(account, timeout=5, otp_sent_at=180)

        self.assertEqual(code, "222222")

    @mock.patch("requests.post")
    def test_fetch_oauth_token_returns_empty_when_probe_gets_malformed_json_on_2xx(self, mock_post):
        mailbox = OutlookMailbox(token_endpoint="https://token.example.test")
        mock_post.side_effect = [
            _FakeResponse(
                200,
                text="not-json",
                json_error=ValueError("malformed json"),
            ),
            _FakeResponse(
                200,
                text="still-not-json",
                json_error=ValueError("malformed json again"),
            ),
        ]

        token = mailbox._fetch_oauth_token(
            email="demo@outlook.com",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        self.assertEqual(token, "")
        attempted_scopes = [
            call.kwargs["data"].get("scope", "")
            for call in mock_post.call_args_list
        ]
        self.assertIn(
            "https://graph.microsoft.com/.default",
            attempted_scopes,
        )
        self.assertIn(
            "https://outlook.office.com/.default offline_access",
            attempted_scopes,
        )

    def test_get_email_moves_account_into_recovery_pool(self):
        mailbox = OutlookMailbox()
        test_engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(test_engine)

        try:
            with Session(test_engine) as session:
                session.add(
                    OutlookAccountModel(
                        email="lease-demo@outlook.com",
                        password="password",
                        client_id="client-id",
                        refresh_token="refresh-token",
                    )
                )
                session.commit()

            with mock.patch("core.db.engine", test_engine):
                account = mailbox.get_email()

            self.assertEqual(account.email, "lease-demo@outlook.com")
            self.assertTrue(account.extra.get("outlook_lease_id"))

            with Session(test_engine) as session:
                available = session.exec(select(OutlookAccountModel)).all()
                leased = session.exec(select(OutlookAccountLeaseModel)).all()

            self.assertEqual(len(available), 0)
            self.assertEqual(len(leased), 1)
            self.assertEqual(leased[0].email, "lease-demo@outlook.com")
            self.assertEqual(leased[0].status, "leased")
        finally:
            test_engine.dispose()

    def test_mark_account_failure_keeps_account_in_recovery_pool(self):
        mailbox = OutlookMailbox()
        test_engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(test_engine)

        try:
            with Session(test_engine) as session:
                session.add(
                    OutlookAccountModel(
                        email="failed-demo@outlook.com",
                        password="password",
                        client_id="client-id",
                        refresh_token="refresh-token",
                    )
                )
                session.commit()

            with mock.patch("core.db.engine", test_engine):
                account = mailbox.get_email()
                mailbox.mark_account_failure(account, error="token_exchange failed")

            with Session(test_engine) as session:
                available = session.exec(select(OutlookAccountModel)).all()
                leased = session.exec(select(OutlookAccountLeaseModel)).all()

            self.assertEqual(len(available), 0)
            self.assertEqual(len(leased), 1)
            self.assertEqual(leased[0].status, "recoverable")
            self.assertEqual(leased[0].last_error, "token_exchange failed")
        finally:
            test_engine.dispose()

    def test_mark_account_success_clears_recovery_record(self):
        mailbox = OutlookMailbox()
        test_engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(test_engine)

        try:
            with Session(test_engine) as session:
                session.add(
                    OutlookAccountModel(
                        email="success-demo@outlook.com",
                        password="password",
                        client_id="client-id",
                        refresh_token="refresh-token",
                    )
                )
                session.commit()

            with mock.patch("core.db.engine", test_engine):
                account = mailbox.get_email()
                mailbox.mark_account_success(account)

            with Session(test_engine) as session:
                available = session.exec(select(OutlookAccountModel)).all()
                leased = session.exec(select(OutlookAccountLeaseModel)).all()

            self.assertEqual(len(available), 0)
            self.assertEqual(len(leased), 0)
        finally:
            test_engine.dispose()


if __name__ == "__main__":
    unittest.main()
