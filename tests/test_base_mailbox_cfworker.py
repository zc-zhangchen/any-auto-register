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

    @patch("requests.request")
    def test_get_email_uses_static_subdomain(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = '{"email":"user@mail.sub.example","token":"token-123"}'
        mock_request.return_value.json.return_value = {
            "email": "user@mail.sub.example",
            "token": "token-123",
        }

        mailbox = create_mailbox(
            "cfworker",
            extra={
                "cfworker_api_url": "https://example.invalid",
                "cfworker_admin_token": "admin-token",
                "cfworker_domain": "sub.example",
                "cfworker_subdomain": "mail",
            },
        )

        mailbox.get_email()

        self.assertEqual(
            mock_request.call_args.kwargs["json"]["domain"],
            "mail.sub.example",
        )

    @patch("requests.request")
    def test_get_email_uses_random_subdomain(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = '{"email":"user@rand.sub.example","token":"token-123"}'
        mock_request.return_value.json.return_value = {
            "email": "user@rand.sub.example",
            "token": "token-123",
        }

        mailbox = create_mailbox(
            "cfworker",
            extra={
                "cfworker_api_url": "https://example.invalid",
                "cfworker_admin_token": "admin-token",
                "cfworker_domain": "sub.example",
                "cfworker_subdomain": "mail",
                "cfworker_random_subdomain": True,
            },
        )

        with patch.object(type(mailbox), "_generate_subdomain_label", return_value="rand"):
            mailbox.get_email()

        self.assertEqual(
            mock_request.call_args.kwargs["json"]["domain"],
            "rand.mail.sub.example",
        )

    @patch("requests.request")
    def test_get_email_auto_fills_to_configured_domain_levels(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = '{"email":"user@l1.l2.github163.com","token":"token-123"}'
        mock_request.return_value.json.return_value = {
            "email": "user@l1.l2.github163.com",
            "token": "token-123",
        }

        mailbox = create_mailbox(
            "cfworker",
            extra={
                "cfworker_api_url": "https://example.invalid",
                "cfworker_admin_token": "admin-token",
                "cfworker_domain": "github163.com",
                "email_domain_level_count": 4,
            },
        )

        with patch.object(type(mailbox), "_generate_subdomain_label", side_effect=["l1", "l2"]):
            mailbox.get_email()

        self.assertEqual(
            mock_request.call_args.kwargs["json"]["domain"],
            "l1.l2.github163.com",
        )

    @patch("requests.request")
    def test_get_email_auto_fill_keeps_configured_subdomain(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = '{"email":"user@l1.pool.github163.com","token":"token-123"}'
        mock_request.return_value.json.return_value = {
            "email": "user@l1.pool.github163.com",
            "token": "token-123",
        }

        mailbox = create_mailbox(
            "cfworker",
            extra={
                "cfworker_api_url": "https://example.invalid",
                "cfworker_admin_token": "admin-token",
                "cfworker_domain": "github163.com",
                "cfworker_subdomain": "pool",
                "email_domain_level_count": 4,
            },
        )

        with patch.object(type(mailbox), "_generate_subdomain_label", return_value="l1"):
            mailbox.get_email()

        self.assertEqual(
            mock_request.call_args.kwargs["json"]["domain"],
            "l1.pool.github163.com",
        )


if __name__ == "__main__":
    unittest.main()
