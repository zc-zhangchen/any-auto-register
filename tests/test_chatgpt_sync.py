import unittest
from unittest import mock

from core.db import AccountModel
from services.chatgpt_sync import backfill_chatgpt_account_to_cpa, build_chatgpt_sync_account


class ChatGPTBackfillTests(unittest.TestCase):
    def _make_account(self) -> AccountModel:
        account = AccountModel(
            platform="chatgpt",
            email="demo@example.com",
            password="secret",
            token="access-token",
            status="registered",
        )
        account.set_extra(
            {
                "access_token": "access-token",
                "session_token": "session-token",
                "mail_provider": "cfworker",
            }
        )
        return account

    def test_build_sync_account_preserves_user_id(self):
        account = self._make_account()
        account.user_id = "acct-123"

        sync_account = build_chatgpt_sync_account(account)

        self.assertEqual(sync_account.user_id, "acct-123")

    def test_backfill_skips_when_remote_auth_exists(self):
        account = self._make_account()
        extra = account.get_extra()
        extra["sync_statuses"] = {
            "cliproxyapi": {
                "uploaded": True,
                "remote_state": "usable",
                "message": "",
            }
        }
        account.set_extra(extra)

        with mock.patch("services.cliproxyapi_sync.sync_chatgpt_cliproxyapi_status") as sync_mock:
            with mock.patch("platforms.chatgpt.status_probe.probe_local_chatgpt_status") as probe_mock:
                result = backfill_chatgpt_account_to_cpa(account, commit=False)

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertFalse(result["uploaded"])
        self.assertIn("远端已存在", result["message"])
        sync_mock.assert_not_called()
        probe_mock.assert_not_called()

    def test_backfill_fails_when_local_probe_invalid(self):
        account = self._make_account()
        extra = account.get_extra()
        extra["sync_statuses"] = {
            "cliproxyapi": {
                "uploaded": False,
                "remote_state": "not_found",
                "message": "未发现",
            }
        }
        account.set_extra(extra)

        with mock.patch("services.cliproxyapi_sync.sync_chatgpt_cliproxyapi_status") as sync_mock:
            with mock.patch(
                "platforms.chatgpt.status_probe.probe_local_chatgpt_status",
                return_value={
                    "auth": {
                        "state": "access_token_invalidated",
                        "http_status": 401,
                        "error_code": "token_invalidated",
                        "message": "invalidated",
                    },
                    "codex": {"state": "skipped_auth_invalid"},
                },
            ):
                with mock.patch("services.chatgpt_sync.upload_account_model_to_cpa") as upload_mock:
                    result = backfill_chatgpt_account_to_cpa(account, commit=False)

        self.assertFalse(result["ok"])
        self.assertFalse(result["uploaded"])
        self.assertFalse(result["skipped"])
        self.assertEqual(account.status, "invalid")
        sync_mock.assert_not_called()
        upload_mock.assert_not_called()

    def test_backfill_uploads_and_resyncs_when_remote_missing_and_local_valid(self):
        account = self._make_account()
        extra = account.get_extra()
        extra["sync_statuses"] = {
            "cliproxyapi": {
                "uploaded": False,
                "remote_state": "not_found",
                "message": "未发现",
            }
        }
        account.set_extra(extra)

        with mock.patch(
            "services.cliproxyapi_sync.sync_chatgpt_cliproxyapi_status",
            side_effect=[
                {
                    "uploaded": True,
                    "remote_state": "usable",
                    "message": "远端可用",
                },
            ],
        ) as sync_mock:
            with mock.patch(
                "platforms.chatgpt.status_probe.probe_local_chatgpt_status",
                return_value={
                    "auth": {
                        "state": "access_token_valid",
                        "http_status": 200,
                        "error_code": "",
                        "message": "ok",
                    },
                    "subscription": {"plan": "free"},
                    "codex": {"state": "usable"},
                },
            ):
                with mock.patch(
                    "services.chatgpt_sync.upload_account_model_to_cpa",
                    return_value=(True, "上传成功"),
                ) as upload_mock:
                    result = backfill_chatgpt_account_to_cpa(account, commit=False)

        self.assertTrue(result["ok"])
        self.assertTrue(result["uploaded"])
        self.assertFalse(result["skipped"])
        self.assertIn("补传完成", result["message"])
        self.assertEqual(sync_mock.call_count, 1)
        upload_mock.assert_called_once()

    def test_backfill_syncs_once_when_cache_missing(self):
        account = self._make_account()

        with mock.patch(
            "services.cliproxyapi_sync.sync_chatgpt_cliproxyapi_status",
            side_effect=[
                {
                    "uploaded": False,
                    "remote_state": "not_found",
                    "message": "未发现",
                },
                {
                    "uploaded": True,
                    "remote_state": "usable",
                    "message": "远端可用",
                },
            ],
        ) as sync_mock:
            with mock.patch(
                "platforms.chatgpt.status_probe.probe_local_chatgpt_status",
                return_value={
                    "auth": {
                        "state": "access_token_valid",
                        "http_status": 200,
                        "error_code": "",
                        "message": "ok",
                    },
                    "subscription": {"plan": "free"},
                    "codex": {"state": "usable"},
                },
            ):
                with mock.patch(
                    "services.chatgpt_sync.upload_account_model_to_cpa",
                    return_value=(True, "上传成功"),
                ):
                    result = backfill_chatgpt_account_to_cpa(account, commit=False)

        self.assertTrue(result["ok"])
        self.assertTrue(result["uploaded"])
        self.assertEqual(sync_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
