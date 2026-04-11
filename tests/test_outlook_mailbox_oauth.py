import unittest
from unittest import mock

from core.base_mailbox import MailboxAccount, OutlookMailbox, create_mailbox


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

    @mock.patch("requests.get")
    def test_wait_for_code_uses_mailapi_backend_for_mailapi_account(self, mock_get):
        mailbox = OutlookMailbox()
        account = MailboxAccount(
            email="demo@outlook.com",
            extra={
                "account_type": "mailapi_url",
                "mailapi_url": "https://mailapi.icu/key?type=html&orderNo=abc123",
            },
        )
        mock_get.return_value = _FakeResponse(
            200,
            text="<html><body>Your OpenAI verification code is 246810</body></html>",
        )

        code = mailbox.wait_for_code(
            account,
            timeout=5,
            before_ids=set(),
        )

        self.assertEqual(code, "246810")
        self.assertTrue(mock_get.call_count >= 1)
        self.assertEqual(
            mock_get.call_args.kwargs.get("timeout"),
            15,
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


if __name__ == "__main__":
    unittest.main()
