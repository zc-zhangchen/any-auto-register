import unittest
from unittest import mock

from services.cliproxyapi_sync import _probe_remote_auth, sync_chatgpt_cliproxyapi_status, sync_chatgpt_cliproxyapi_status_batch


class DummyAccount:
    def __init__(self, *, email="demo@example.com", token="", extra=None, user_id=""):
        self.email = email
        self.token = token
        self.extra = dict(extra or {})
        self.user_id = user_id


class CliproxyapiSyncTests(unittest.TestCase):
    def test_sync_returns_unreachable_when_service_down(self):
        account = DummyAccount()

        with mock.patch(
            "services.cliproxyapi_sync.list_auth_files",
            side_effect=RuntimeError("CLIProxyAPI 无法连接，请确认服务已启动或 API URL 是否正确：http://127.0.0.1:8317"),
        ):
            result = sync_chatgpt_cliproxyapi_status(account, api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertEqual(result["remote_state"], "unreachable")
        self.assertIn("无法连接", result["message"])

    def test_sync_retries_list_auth_files_until_success(self):
        account = DummyAccount(email="demo@example.com", user_id="acct-123")
        auth_files = [
            {
                "name": "demo@example.com.json",
                "provider": "codex",
                "email": "demo@example.com",
                "auth_index": "auth-001",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            }
        ]

        with mock.patch(
            "services.cliproxyapi_sync.list_auth_files",
            side_effect=[
                RuntimeError("CLIProxyAPI 无法连接，请确认服务已启动或 API URL 是否正确：http://127.0.0.1:8317"),
                RuntimeError("CLIProxyAPI 请求超时：http://127.0.0.1:8317"),
                auth_files,
            ],
        ) as list_mock:
            with mock.patch(
                "services.cliproxyapi_sync._probe_remote_auth",
                return_value={
                    "last_probe_at": "2026-03-31T00:00:00Z",
                    "last_probe_status_code": 200,
                    "last_probe_error_code": "",
                    "last_probe_message": "ok",
                    "remote_state": "usable",
                },
            ):
                with mock.patch("services.cliproxyapi_sync.time.sleep") as sleep_mock:
                    result = sync_chatgpt_cliproxyapi_status(account, api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertTrue(result["uploaded"])
        self.assertEqual(result["remote_state"], "usable")
        self.assertEqual(list_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_sync_returns_not_found_when_remote_auth_missing(self):
        account = DummyAccount(token="access-token")
        account.access_token = "access-token"

        with mock.patch("services.cliproxyapi_sync.list_auth_files", return_value=[]):
            with mock.patch(
                "platforms.chatgpt.cpa_upload.upload_to_cpa",
                return_value=(False, "上传失败: HTTP 401"),
            ):
                result = sync_chatgpt_cliproxyapi_status(account, api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertFalse(result["uploaded"])
        self.assertIn("上传失败", result["message"])

    def test_sync_uses_matching_codex_auth_and_probe(self):
        account = DummyAccount(email="demo@example.com", user_id="acct-123")
        auth_files = [
            {
                "name": "demo@example.com.json",
                "provider": "codex",
                "email": "demo@example.com",
                "auth_index": "auth-001",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            }
        ]

        with mock.patch("services.cliproxyapi_sync.list_auth_files", return_value=auth_files):
            with mock.patch(
                "services.cliproxyapi_sync._probe_remote_auth",
                return_value={
                    "last_probe_at": "2026-03-31T00:00:00Z",
                    "last_probe_status_code": 200,
                    "last_probe_error_code": "",
                    "last_probe_message": "ok",
                    "remote_state": "usable",
                },
            ):
                result = sync_chatgpt_cliproxyapi_status(account, api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertTrue(result["uploaded"])
        self.assertEqual(result["auth_index"], "auth-001")
        self.assertEqual(result["remote_state"], "usable")

    def test_sync_matches_codex_auth_by_user_id_when_email_lookup_is_missing(self):
        account = DummyAccount(email="", user_id="acct-123")
        auth_files = [
            {
                "name": "acct-123.json",
                "provider": "codex",
                "auth_index": "auth-123",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            }
        ]

        with mock.patch("services.cliproxyapi_sync.list_auth_files", return_value=auth_files):
            with mock.patch(
                "services.cliproxyapi_sync._probe_remote_auth",
                return_value={
                    "last_probe_at": "2026-03-31T00:00:00Z",
                    "last_probe_status_code": 200,
                    "last_probe_error_code": "",
                    "last_probe_message": "ok",
                    "remote_state": "usable",
                },
            ):
                result = sync_chatgpt_cliproxyapi_status(account, api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertTrue(result["uploaded"])
        self.assertEqual(result["auth_index"], "auth-123")
        self.assertEqual(result["remote_state"], "usable")

    def test_sync_seeds_missing_remote_auth_from_local_account(self):
        account = DummyAccount(email="demo@example.com", token="access-token", user_id="acct-123")
        account.access_token = "access-token"
        account.refresh_token = "refresh-token"
        account.id_token = ""
        auth_files = [
            {
                "name": "demo@example.com.json",
                "provider": "codex",
                "email": "demo@example.com",
                "auth_index": "auth-001",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            }
        ]

        with mock.patch("services.cliproxyapi_sync.list_auth_files", side_effect=[[], auth_files]):
            with mock.patch("services.cliproxyapi_sync.time.sleep"):
                with mock.patch(
                    "platforms.chatgpt.cpa_upload.upload_to_cpa",
                    return_value=(True, "上传成功"),
                ) as upload_mock:
                    with mock.patch(
                        "services.cliproxyapi_sync._probe_remote_auth",
                        return_value={
                            "last_probe_at": "2026-03-31T00:00:00Z",
                            "last_probe_status_code": 200,
                            "last_probe_error_code": "",
                            "last_probe_message": "ok",
                            "remote_state": "usable",
                        },
                    ):
                        result = sync_chatgpt_cliproxyapi_status(account, api_url="http://localhost:8317", api_key="islam")

        self.assertTrue(result["uploaded"])
        self.assertEqual(result["remote_state"], "usable")
        self.assertEqual(result["auth_index"], "auth-001")
        self.assertTrue(result.get("seeded"))
        upload_mock.assert_called_once()

    def test_sync_seeds_missing_remote_auth_from_sqlite_row_when_account_object_lacks_token(self):
        account = DummyAccount(email="demo@example.com", token="", user_id="acct-123")
        account.access_token = ""
        account.refresh_token = ""
        account.id_token = ""
        sqlite_row = mock.Mock()
        sqlite_row.id = 101
        sqlite_row.email = "demo@example.com"
        sqlite_row.user_id = "acct-123"
        sqlite_row.platform = "chatgpt"
        sqlite_row.password = "pw"
        sqlite_row.token = "sqlite-access-token"
        sqlite_row.get_extra.return_value = {
            "access_token": "sqlite-access-token",
            "refresh_token": "sqlite-refresh-token",
        }
        auth_files = [
            {
                "name": "demo@example.com.json",
                "provider": "codex",
                "email": "demo@example.com",
                "auth_index": "auth-101",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            }
        ]

        with mock.patch("services.cliproxyapi_sync._load_local_chatgpt_account", return_value=sqlite_row):
            with mock.patch("services.cliproxyapi_sync.list_auth_files", side_effect=[[], auth_files]):
                with mock.patch("services.cliproxyapi_sync.time.sleep"):
                    with mock.patch(
                        "platforms.chatgpt.cpa_upload.upload_to_cpa",
                        return_value=(True, "上传成功"),
                    ) as upload_mock:
                        with mock.patch(
                            "services.cliproxyapi_sync._probe_remote_auth",
                            return_value={
                                "last_probe_at": "2026-03-31T00:00:00Z",
                                "last_probe_status_code": 200,
                                "last_probe_error_code": "",
                                "last_probe_message": "ok",
                                "remote_state": "usable",
                            },
                        ):
                            result = sync_chatgpt_cliproxyapi_status(account, api_url="http://localhost:8317", api_key="islam")

        self.assertTrue(result["uploaded"])
        self.assertEqual(result["remote_state"], "usable")
        self.assertEqual(result["auth_index"], "auth-101")
        self.assertTrue(result.get("seeded"))
        upload_mock.assert_called_once()

    def test_probe_remote_auth_maps_token_invalidated(self):
        with mock.patch(
            "services.cliproxyapi_sync._request_json",
            return_value={
                "status_code": 401,
                "header": {
                    "X-Openai-Ide-Error-Code": ["token_invalidated"],
                },
                "body": '{"error":{"code":"token_invalidated","message":"Your authentication token has been invalidated."}}',
            },
        ):
            result = _probe_remote_auth("auth-001", "acct-123", api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertEqual(result["last_probe_status_code"], 401)
        self.assertEqual(result["last_probe_error_code"], "token_invalidated")
        self.assertEqual(result["remote_state"], "access_token_invalidated")

    def test_probe_remote_auth_maps_account_deactivated(self):
        with mock.patch(
            "services.cliproxyapi_sync._request_json",
            return_value={
                "status_code": 403,
                "header": {},
                "body": '{"error":{"code":"account_deactivated","message":"You do not have an account because it has been deleted or deactivated."}}',
            },
        ):
            result = _probe_remote_auth("auth-001", "acct-123", api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertEqual(result["last_probe_status_code"], 403)
        self.assertEqual(result["last_probe_error_code"], "account_deactivated")
        self.assertEqual(result["remote_state"], "account_deactivated")

    def test_sync_retries_remote_probe_until_success(self):
        account = DummyAccount(email="demo@example.com", user_id="acct-123")
        auth_files = [
            {
                "name": "demo@example.com.json",
                "provider": "codex",
                "email": "demo@example.com",
                "auth_index": "auth-001",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            }
        ]

        with mock.patch("services.cliproxyapi_sync.list_auth_files", return_value=auth_files):
            with mock.patch(
                "services.cliproxyapi_sync._probe_remote_auth",
                side_effect=[
                    RuntimeError("CLIProxyAPI 请求超时：http://127.0.0.1:8317"),
                    RuntimeError("CLIProxyAPI 无法连接，请确认服务已启动或 API URL 是否正确：http://127.0.0.1:8317"),
                    {
                        "last_probe_at": "2026-03-31T00:00:00Z",
                        "last_probe_status_code": 200,
                        "last_probe_error_code": "",
                        "last_probe_message": "ok",
                        "remote_state": "usable",
                    },
                ],
            ) as probe_mock:
                with mock.patch("services.cliproxyapi_sync.time.sleep") as sleep_mock:
                    result = sync_chatgpt_cliproxyapi_status(account, api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertTrue(result["uploaded"])
        self.assertEqual(result["remote_state"], "usable")
        self.assertEqual(probe_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_batch_sync_fetches_auth_files_once(self):
        accounts = [
            DummyAccount(email="a@example.com", user_id="acct-a"),
            DummyAccount(email="missing@example.com", user_id="acct-missing"),
            DummyAccount(email="b@example.com", user_id="acct-b"),
        ]
        accounts[0].id = 1
        accounts[1].id = 2
        accounts[2].id = 3

        auth_files = [
            {
                "name": "a@example.com.json",
                "provider": "codex",
                "email": "a@example.com",
                "auth_index": "auth-a",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            },
            {
                "name": "b@example.com.json",
                "provider": "codex",
                "email": "b@example.com",
                "auth_index": "auth-b",
                "status": "active",
                "status_message": "",
                "unavailable": False,
            },
        ]

        with mock.patch("services.cliproxyapi_sync.list_auth_files", return_value=auth_files) as list_mock:
            with mock.patch(
                "services.cliproxyapi_sync._probe_remote_auth",
                side_effect=[
                    {
                        "last_probe_at": "2026-03-31T00:00:00Z",
                        "last_probe_status_code": 200,
                        "last_probe_error_code": "",
                        "last_probe_message": "ok",
                        "remote_state": "usable",
                    },
                    {
                        "last_probe_at": "2026-03-31T00:00:01Z",
                        "last_probe_status_code": 401,
                        "last_probe_error_code": "token_invalidated",
                        "last_probe_message": "invalidated",
                        "remote_state": "access_token_invalidated",
                    },
                ],
            ) as probe_mock:
                with mock.patch("services.cliproxyapi_sync.time.sleep") as sleep_mock:
                    result = sync_chatgpt_cliproxyapi_status_batch(accounts, api_url="http://127.0.0.1:8317", api_key="demo")

        self.assertEqual(list_mock.call_count, 1)
        self.assertEqual(probe_mock.call_count, 2)
        self.assertEqual(result[1]["remote_state"], "usable")
        self.assertEqual(result[2]["remote_state"], "not_found")
        self.assertEqual(result[3]["remote_state"], "access_token_invalidated")
        self.assertEqual(sleep_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
