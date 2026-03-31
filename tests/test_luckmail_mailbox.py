import unittest
from unittest import mock

from core.base_mailbox import LuckMailMailbox, MailboxAccount
from core.luckmail.models import TokenCode, TokenMailItem, TokenMailList


class LuckMailMailboxTests(unittest.TestCase):
    def _build_mailbox(self):
        mailbox = LuckMailMailbox.__new__(LuckMailMailbox)
        mailbox._client = mock.Mock()
        mailbox._project_code = "openai"
        mailbox._email_type = None
        mailbox._domain = None
        mailbox._order_no = None
        mailbox._token = "tok_demo"
        mailbox._email = "demo@example.com"
        mailbox._log_fn = None
        return mailbox

    def test_wait_for_code_skips_excluded_purchase_code_and_returns_fresh_mail_code(self):
        mailbox = self._build_mailbox()
        mailbox._client.user.wait_for_token_code.return_value = TokenCode(
            email_address="demo@example.com",
            project="openai",
            has_new_mail=True,
            verification_code="111111",
            mail={"subject": "Your OpenAI code is 111111"},
        )
        mailbox._client.user.get_token_mails.return_value = TokenMailList(
            email_address="demo@example.com",
            project="openai",
            mails=[
                TokenMailItem(message_id="m1", subject="Your OpenAI code is 111111"),
                TokenMailItem(message_id="m2", subject="Your OpenAI code is 222222"),
            ],
        )

        code = mailbox.wait_for_code(
            MailboxAccount(email="demo@example.com", account_id="tok_demo"),
            timeout=8,
            exclude_codes={"111111"},
        )

        self.assertEqual(code, "222222")


if __name__ == "__main__":
    unittest.main()
