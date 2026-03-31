import unittest
from unittest.mock import patch

from core.base_mailbox import MailboxAccount, create_mailbox


class CFWorkerMailboxTests(unittest.TestCase):
    def _build_mailbox(self):
        return create_mailbox(
            "cfworker",
            extra={
                "cfworker_api_url": "https://example.invalid",
                "cfworker_admin_token": "admin-token",
                "cfworker_domain": "mail.example",
            },
        )

    @patch("requests.request")
    def test_get_email_issues_single_request_via_factory_mailbox(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = '{"email":"user@mail.example","token":"token-123"}'
        mock_request.return_value.json.return_value = {
            "email": "user@mail.example",
            "token": "token-123",
        }

        mailbox = self._build_mailbox()

        account = mailbox.get_email()

        self.assertEqual(account.email, "user@mail.example")
        self.assertEqual(account.account_id, "token-123")
        mock_request.assert_called_once_with(
            "POST",
            "https://example.invalid/admin/new_address",
            params=None,
            json={"enablePrefix": True, "name": unittest.mock.ANY, "domain": "mail.example"},
            headers={
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "x-admin-auth": "admin-token",
            },
            proxies=None,
            timeout=15,
        )

    @patch("requests.request")
    def test_get_current_ids_issues_single_request_via_factory_mailbox(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = '{"results":[{"id":101},{"id":202}]}'
        mock_request.return_value.json.return_value = {
            "results": [
                {"id": 101},
                {"id": 202},
            ]
        }
        mailbox = self._build_mailbox()
        account = MailboxAccount(email="user@mail.example")

        ids = mailbox.get_current_ids(account)

        self.assertEqual(ids, {"101", "202"})
        mock_request.assert_called_once_with(
            "GET",
            "https://example.invalid/admin/mails",
            params={"limit": 20, "offset": 0, "address": "user@mail.example"},
            json=None,
            headers={
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "x-admin-auth": "admin-token",
            },
            proxies=None,
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
