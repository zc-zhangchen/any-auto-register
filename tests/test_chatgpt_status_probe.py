import unittest
from unittest import mock

from platforms.chatgpt.status_probe import ProbeHTTPResult, probe_local_chatgpt_status


class DummyAccount:
    def __init__(self, *, token="", access_token="", refresh_token="", session_token="", extra=None, user_id=""):
        self.email = "demo@example.com"
        self.token = token
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.session_token = session_token
        self.extra = dict(extra or {})
        self.user_id = user_id


class ChatGPTStatusProbeTests(unittest.TestCase):
    def test_probe_marks_missing_access_token(self):
        account = DummyAccount()

        result = probe_local_chatgpt_status(account)

        self.assertEqual(result["auth"]["state"], "missing_access_token")
        self.assertEqual(result["codex"]["state"], "skipped_auth_invalid")

    def test_probe_marks_invalidated_token(self):
        account = DummyAccount(token="access-token")

        with mock.patch(
            "platforms.chatgpt.status_probe._probe_backend_me",
            return_value=ProbeHTTPResult(
                status_code=401,
                headers={},
                body_text='{"error":{"code":"token_invalidated"}}',
                body_json={"error": {"code": "token_invalidated", "message": "invalidated"}},
                error_code="token_invalidated",
                message="invalidated",
            ),
        ):
            result = probe_local_chatgpt_status(account)

        self.assertEqual(result["auth"]["state"], "access_token_invalidated")
        self.assertEqual(result["codex"]["state"], "skipped_auth_invalid")

    def test_probe_reads_duck_typed_access_token_attributes(self):
        account = DummyAccount(access_token="access-token", session_token="session-token")

        with mock.patch(
            "platforms.chatgpt.status_probe._probe_backend_me",
            return_value=ProbeHTTPResult(
                status_code=401,
                headers={},
                body_text='{"error":{"code":"token_invalidated"}}',
                body_json={"error": {"code": "token_invalidated", "message": "invalidated"}},
                error_code="token_invalidated",
                message="invalidated",
            ),
        ):
            result = probe_local_chatgpt_status(account)

        self.assertEqual(result["auth"]["state"], "access_token_invalidated")
        self.assertTrue(result["auth"]["refresh_available"])

    def test_probe_marks_account_deactivated(self):
        account = DummyAccount(token="access-token")

        with mock.patch(
            "platforms.chatgpt.status_probe._probe_backend_me",
            return_value=ProbeHTTPResult(
                status_code=403,
                headers={},
                body_text='{"error":{"code":"account_deactivated","message":"You do not have an account because it has been deleted or deactivated."}}',
                body_json={"error": {"code": "account_deactivated", "message": "You do not have an account because it has been deleted or deactivated."}},
                error_code="account_deactivated",
                message="You do not have an account because it has been deleted or deactivated.",
            ),
        ):
            result = probe_local_chatgpt_status(account)

        self.assertEqual(result["auth"]["state"], "account_deactivated")
        self.assertEqual(result["codex"]["state"], "skipped_auth_invalid")

    def test_probe_extracts_plan_and_quota_state(self):
        account = DummyAccount(token="access-token", user_id="acct-123")

        with mock.patch(
            "platforms.chatgpt.status_probe._probe_backend_me",
            return_value=ProbeHTTPResult(
                status_code=200,
                headers={},
                body_text='{"plan_type":"chatgptplusplan"}',
                body_json={"plan_type": "chatgptplusplan"},
                error_code="",
                message="ok",
            ),
        ):
            with mock.patch(
                "platforms.chatgpt.status_probe._probe_codex_usage",
                return_value=ProbeHTTPResult(
                    status_code=429,
                    headers={},
                    body_text='{"error":{"type":"usage_limit_reached"}}',
                    body_json={"error": {"type": "usage_limit_reached"}},
                    error_code="",
                    message="usage_limit_reached",
                ),
            ):
                result = probe_local_chatgpt_status(account)

        self.assertEqual(result["auth"]["state"], "access_token_valid")
        self.assertEqual(result["subscription"]["plan"], "plus")
        self.assertEqual(result["codex"]["state"], "quota_exhausted")


if __name__ == "__main__":
    unittest.main()
