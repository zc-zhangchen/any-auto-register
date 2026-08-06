import unittest
from unittest.mock import patch

from core.base_mailbox import MailboxAccount, create_mailbox


class GPTMailMailboxTests(unittest.TestCase):
    def _build_mailbox(self, **extra):
        config = {
            "gptmail_base_url": "https://mail.chatgpt.org.uk",
            "gptmail_api_key": "gpt-test",
            "gptmail_mode": "api",
        }
        config.update(extra)
        return create_mailbox("gptmail", extra=config)

    @patch("requests.request")
    def test_get_email_issues_generate_request(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "success": True,
            "data": {"email": "demo@example.com"},
        }

        mailbox = self._build_mailbox()
        account = mailbox.get_email()

        self.assertEqual(account.email, "demo@example.com")
        self.assertEqual(account.account_id, "demo@example.com")
        mock_request.assert_called_once_with(
            "GET",
            "https://mail.chatgpt.org.uk/api/generate-email",
            params=None,
            json=None,
            headers={
                "accept": "application/json",
                "X-API-Key": "gpt-test",
            },
            proxies=None,
            timeout=15,
        )

    @patch("requests.request")
    def test_get_email_can_compose_local_address_when_domain_configured(self, mock_request):
        mailbox = self._build_mailbox(gptmail_domain="known.example")

        with patch.object(type(mailbox), "_generate_local_part", return_value="demo1234"):
            account = mailbox.get_email()

        self.assertEqual(account.email, "demo1234@known.example")
        self.assertEqual(account.extra["domain"], "known.example")
        self.assertEqual(account.extra["mode"], "api")
        mock_request.assert_not_called()

    @patch("core.gptmail_automation.GPTMailAutomationClient.generate_email")
    def test_get_email_uses_automation_mode_without_api_request(self, mock_generate_email):
        mock_generate_email.return_value = "auto@example.com"

        mailbox = self._build_mailbox(gptmail_mode="automation")
        account = mailbox.get_email()

        self.assertEqual(account.email, "auto@example.com")
        self.assertEqual(account.extra["mode"], "automation")
        mock_generate_email.assert_called_once_with()

    @patch("requests.request")
    def test_get_current_ids_reads_inbox_messages(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "success": True,
            "data": {
                "emails": [
                    {"id": "m1", "subject": "Hello"},
                    {"id": "m2", "subject": "World"},
                ]
            },
        }

        mailbox = self._build_mailbox()
        ids = mailbox.get_current_ids(MailboxAccount(email="demo@example.com"))

        self.assertEqual(ids, {"m1", "m2"})
        mock_request.assert_called_once_with(
            "GET",
            "https://mail.chatgpt.org.uk/api/emails",
            params={"email": "demo@example.com"},
            json=None,
            headers={
                "accept": "application/json",
                "X-API-Key": "gpt-test",
            },
            proxies=None,
            timeout=10,
        )

    @patch("core.gptmail_automation.GPTMailAutomationClient.get_emails")
    def test_get_current_ids_reads_automation_inbox_messages(self, mock_get_emails):
        mock_get_emails.return_value = [
            {"id": "m1", "subject": "Hello"},
            {"message_id": "m2", "subject": "World"},
        ]

        mailbox = self._build_mailbox(gptmail_mode="automation")
        ids = mailbox.get_current_ids(MailboxAccount(email="demo@example.com"))

        self.assertEqual(ids, {"m1", "m2"})
        mock_get_emails.assert_called_once_with("demo@example.com")

    @patch("time.sleep", return_value=None)
    @patch("requests.request")
    def test_wait_for_code_skips_excluded_codes_and_fetches_detail(self, mock_request, _sleep):
        mock_request.side_effect = [
            _response(
                {
                    "success": True,
                    "data": {
                        "emails": [
                            {"id": "m1", "subject": "Your code: 111111"},
                        ]
                    },
                }
            ),
            _response(
                {
                    "success": True,
                    "data": {
                        "id": "m1",
                        "subject": "Your code: 111111",
                        "content": "111111",
                    },
                }
            ),
            _response(
                {
                    "success": True,
                    "data": {
                        "emails": [
                            {"id": "m1", "subject": "Your code: 111111"},
                            {"id": "m2", "subject": "Your code: 222222"},
                        ]
                    },
                }
            ),
            _response(
                {
                    "success": True,
                    "data": {
                        "id": "m2",
                        "subject": "Your code: 222222",
                        "content": "verification code 222222",
                    },
                }
            ),
        ]

        mailbox = self._build_mailbox()
        code = mailbox.wait_for_code(
            MailboxAccount(email="demo@example.com"),
            timeout=5,
            exclude_codes={"111111"},
        )

        self.assertEqual(code, "222222")
        self.assertEqual(mock_request.call_count, 4)

    @patch("time.sleep", return_value=None)
    @patch("core.gptmail_automation.GPTMailAutomationClient.get_emails")
    def test_wait_for_code_reads_automation_messages(self, mock_get_emails, _sleep):
        mock_get_emails.side_effect = [
            [{"id": "m1", "subject": "Your code: 111111", "content": "111111"}],
            [
                {"id": "m1", "subject": "Your code: 111111", "content": "111111"},
                {"id": "m2", "subject": "Your code: 222222", "content": "verification code 222222"},
            ],
        ]

        mailbox = self._build_mailbox(gptmail_mode="automation")
        code = mailbox.wait_for_code(
            MailboxAccount(email="demo@example.com"),
            timeout=5,
            exclude_codes={"111111"},
        )

        self.assertEqual(code, "222222")
        self.assertEqual(mock_get_emails.call_count, 2)


def _response(payload, status_code=200):
    response = unittest.mock.Mock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = ""
    return response


if __name__ == "__main__":
    unittest.main()
