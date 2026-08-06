import unittest
from email.message import EmailMessage
from unittest.mock import patch

from core.base_mailbox import MailboxAccount, create_mailbox


class _FakeImapConnection:
    def __init__(self, messages_by_uid):
        self._messages_by_uid = messages_by_uid
        self.logged_out = False
        self.capabilities = (b"IMAP4rev1", b"IDLE")

    def uid(self, command, uid, args):
        if str(command).lower() != "fetch":
            return "NO", []
        raw = self._messages_by_uid.get(str(uid))
        if raw is None:
            return "NO", []
        return "OK", [(b"1 (RFC822 {0})".replace(b"0", str(len(raw)).encode()), raw)]

    def logout(self):
        self.logged_out = True


class CFRoutingMailboxTests(unittest.TestCase):
    def _build_mailbox(self, **extra):
        config = {
            "cfrouting_domain": "example.com",
            "cfrouting_imap_server": "imap.qq.com",
            "cfrouting_imap_port": 993,
            "cfrouting_username": "demo@qq.com",
            "cfrouting_password": "secret",
            "cfrouting_mailboxes": "INBOX",
        }
        config.update(extra)
        return create_mailbox("cfrouting", extra=config)

    def test_message_matches_alias_scans_custom_headers(self):
        mailbox = self._build_mailbox()
        message = EmailMessage()
        message["Subject"] = "Your verification code"
        message["X-QQ-Envelope-To"] = "demo1234@example.com"
        message.set_content("verification code 123456")

        matched = mailbox._message_matches_alias(message, "demo1234@example.com")

        self.assertTrue(matched)

    def test_wait_for_code_falls_back_to_single_new_code_when_alias_header_missing(self):
        mailbox = self._build_mailbox()
        account = MailboxAccount(email="demo1234@example.com")

        message = EmailMessage()
        message["Subject"] = "Your verification code"
        message["From"] = "noreply@example.net"
        message["To"] = "demo@qq.com"
        message.set_content("verification code 123456")
        raw_message = message.as_bytes()
        imap_conn = _FakeImapConnection({"101": raw_message})

        with patch.object(type(mailbox), "_open_imap", return_value=imap_conn), patch.object(
            type(mailbox),
            "_fetch_recent_message_uids",
            return_value=["101"],
        ):
            code = mailbox.wait_for_code(account, timeout=5)

        self.assertEqual(code, "123456")
        self.assertTrue(imap_conn.logged_out)

    def test_wait_for_code_rescans_immediately_after_idle_event(self):
        mailbox = self._build_mailbox()
        account = MailboxAccount(email="demo1234@example.com")

        message = EmailMessage()
        message["Subject"] = "Your verification code"
        message["X-QQ-Envelope-To"] = "demo1234@example.com"
        message.set_content("verification code 654321")
        raw_message = message.as_bytes()
        imap_conn = _FakeImapConnection({"101": raw_message})

        with patch.object(type(mailbox), "_open_imap", return_value=imap_conn), patch.object(
            type(mailbox),
            "_fetch_recent_message_uids",
            side_effect=[[], ["101"]],
        ) as mock_fetch, patch.object(
            type(mailbox),
            "_idle_wait_for_mailbox_event",
            return_value=True,
        ) as mock_idle:
            code = mailbox.wait_for_code(account, timeout=5)

        self.assertEqual(code, "654321")
        self.assertEqual(mock_fetch.call_count, 2)
        mock_idle.assert_called_once()
        self.assertTrue(imap_conn.logged_out)


if __name__ == "__main__":
    unittest.main()
