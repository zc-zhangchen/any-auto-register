import unittest
from unittest.mock import patch

from core.base_mailbox import MailboxAccount, create_mailbox


class TempMailOrgMailboxTests(unittest.TestCase):
    def _build_mailbox(self, **extra):
        config = {
            "tempmailorg_api_url": "https://web2.temp-mail.org",
        }
        config.update(extra)
        return create_mailbox("tempmailorg", extra=config)

    @patch("requests.request")
    def test_get_email_issues_mailbox_request(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "mailbox": "demo@example.com",
            "token": "token-123",
        }

        mailbox = self._build_mailbox()
        account = mailbox.get_email()

        self.assertEqual(account.email, "demo@example.com")
        self.assertEqual(account.account_id, "token-123")
        self.assertEqual(account.extra["provider"], "tempmailorg")
        mock_request.assert_called_once_with(
            "POST",
            "https://web2.temp-mail.org/mailbox",
            params=None,
            json=None,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": "https://web2.temp-mail.org",
                "Referer": "https://web2.temp-mail.org",
            },
            proxies=None,
            timeout=10,
            verify=False,
        )

    @patch("time.sleep", return_value=None)
    @patch("requests.request")
    def test_get_email_retries_on_too_many_requests(self, mock_request, _sleep):
        mock_request.side_effect = [
            _response(
                {
                    "errorMessage": "Too Many Request",
                    "errorName": "TooManyRequestsException",
                },
                status_code=429,
            ),
            _response(
                {
                    "mailbox": "retry@example.com",
                    "token": "retry-token",
                }
            ),
        ]

        mailbox = self._build_mailbox()
        account = mailbox.get_email()

        self.assertEqual(account.email, "retry@example.com")
        self.assertEqual(account.account_id, "retry-token")
        self.assertEqual(mock_request.call_count, 2)

    @patch("time.sleep", return_value=None)
    @patch("requests.request")
    def test_get_email_does_not_retry_other_client_errors(self, mock_request, _sleep):
        mock_request.return_value = _response(
            {
                "errorMessage": "Bad Request",
                "errorName": "BadRequestException",
            },
            status_code=400,
        )

        mailbox = self._build_mailbox()

        with self.assertRaisesRegex(RuntimeError, "Bad Request"):
            mailbox.get_email()

        self.assertEqual(mock_request.call_count, 1)

    @patch("requests.request")
    def test_get_current_ids_reads_messages_with_bearer_token(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "messages": [
                {
                    "from": "alpha@example.com",
                    "subject": "hello",
                    "receivedAt": "2026-04-05T08:00:00Z",
                    "bodyPreview": "one",
                },
                {
                    "from": "beta@example.com",
                    "subject": "world",
                    "receivedAt": "2026-04-05T08:01:00Z",
                    "bodyPreview": "two",
                },
            ]
        }

        mailbox = self._build_mailbox()
        ids = mailbox.get_current_ids(
            MailboxAccount(email="demo@example.com", account_id="token-123")
        )

        self.assertEqual(len(ids), 2)
        self.assertTrue(all(isinstance(item, str) and item for item in ids))
        mock_request.assert_called_once_with(
            "GET",
            "https://web2.temp-mail.org/messages",
            params=None,
            json=None,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": "https://web2.temp-mail.org",
                "Referer": "https://web2.temp-mail.org",
                "Cache-Control": "no-cache",
                "Authorization": "Bearer token-123",
            },
            proxies=None,
            timeout=30,
            verify=False,
        )

    @patch("time.sleep", return_value=None)
    @patch("requests.request")
    def test_wait_for_code_skips_excluded_subject_code(self, mock_request, _sleep):
        mock_request.side_effect = [
            _response(
                {
                    "messages": [
                        {
                            "from": "no-reply@example.com",
                            "subject": "Your code 111111",
                            "receivedAt": "2026-04-05T08:00:00Z",
                            "bodyPreview": "111111",
                        },
                    ]
                }
            ),
            _response(
                {
                    "messages": [
                        {
                            "from": "no-reply@example.com",
                            "subject": "Your code 111111",
                            "receivedAt": "2026-04-05T08:00:00Z",
                            "bodyPreview": "111111",
                        },
                        {
                            "from": "no-reply@example.com",
                            "subject": "Your code 222222",
                            "receivedAt": "2026-04-05T08:01:00Z",
                            "bodyPreview": "222222",
                        },
                    ]
                }
            ),
        ]

        mailbox = self._build_mailbox()
        code = mailbox.wait_for_code(
            MailboxAccount(email="demo@example.com", account_id="token-123"),
            timeout=5,
            exclude_codes={"111111"},
        )

        self.assertEqual(code, "222222")
        self.assertEqual(mock_request.call_count, 2)


def _response(payload, status_code=200):
    response = unittest.mock.Mock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = ""
    return response


if __name__ == "__main__":
    unittest.main()
