import unittest
from unittest import mock

from services.external_sync import sync_account


class DummyAccount:
    def __init__(self, *, platform="chatgpt", email="demo@example.com", token="at-token", extra=None):
        self.platform = platform
        self.email = email
        self.token = token
        self.extra = dict(extra or {})
        self.id = None

    def get_extra(self):
        return dict(self.extra)


def _config_getter(values: dict[str, str]):
    def _get(key: str, default: str = "") -> str:
        return values.get(key, default)

    return _get


class ExternalSyncContributionModeTests(unittest.TestCase):
    def test_contribution_enabled_uploads_only_to_contribution_server(self):
        account = DummyAccount()
        cfg = {
            "contribution_enabled": "1",
            "contribution_server_url": "http://contribution.local:7317",
            "contribution_key": "pk-public-1",
            "cpa_api_url": "http://cpa.local",
            "codex_proxy_url": "http://codex.local",
            "sub2api_api_url": "http://sub2api.local",
            "sub2api_api_key": "sub2-key",
        }

        with mock.patch("core.config_store.config_store.get", side_effect=_config_getter(cfg)):
            with mock.patch("services.external_sync.upload_chatgpt_account_to_cpa", return_value=(True, "ok")) as upload_mock:
                with mock.patch("services.external_sync.persist_cpa_sync_result") as persist_mock:
                    result = sync_account(account)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Contribution")
        self.assertTrue(result[0]["ok"])
        upload_mock.assert_called_once_with(
            account,
            api_url="http://contribution.local:7317",
            api_key="pk-public-1",
        )
        persist_mock.assert_called_once_with(account, True, "ok")

    def test_contribution_enabled_without_server_url_fails_fast(self):
        account = DummyAccount()
        cfg = {
            "contribution_enabled": "true",
            "contribution_server_url": "",
            "contribution_key": "pk-public-1",
        }

        with mock.patch("core.config_store.config_store.get", side_effect=_config_getter(cfg)):
            with mock.patch("services.external_sync.upload_chatgpt_account_to_cpa") as upload_mock:
                with mock.patch("services.external_sync.persist_cpa_sync_result") as persist_mock:
                    result = sync_account(account)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Contribution")
        self.assertFalse(result[0]["ok"])
        self.assertIn("未配置", result[0]["msg"])
        upload_mock.assert_not_called()
        persist_mock.assert_called_once()

    def test_contribution_disabled_keeps_existing_cpa_sync(self):
        account = DummyAccount()
        cfg = {
            "contribution_enabled": "0",
            "cpa_api_url": "http://cpa.local",
        }

        with mock.patch("core.config_store.config_store.get", side_effect=_config_getter(cfg)):
            with mock.patch("services.external_sync.upload_chatgpt_account_to_cpa", return_value=(True, "ok")) as upload_mock:
                with mock.patch("services.external_sync.persist_cpa_sync_result") as persist_mock:
                    result = sync_account(account)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "CPA")
        upload_mock.assert_called_once_with(account)
        persist_mock.assert_called_once_with(account, True, "ok")

    def test_cpa_disabled_skips_auto_upload_but_keeps_configuration(self):
        account = DummyAccount()
        cfg = {
            "contribution_enabled": "0",
            "cpa_enabled": "0",
            "cpa_api_url": "http://cpa.local",
        }

        with mock.patch("core.config_store.config_store.get", side_effect=_config_getter(cfg)):
            with mock.patch("services.external_sync.upload_chatgpt_account_to_cpa") as upload_mock:
                with mock.patch("services.external_sync.persist_cpa_sync_result") as persist_mock:
                    result = sync_account(account)

        self.assertEqual(result, [])
        upload_mock.assert_not_called()
        persist_mock.assert_not_called()

    def test_sub2api_enabled_uploads_and_persists_sync_status(self):
        account = DummyAccount()
        cfg = {
            "contribution_enabled": "0",
            "sub2api_enabled": "1",
            "sub2api_api_url": "http://sub2api.local",
            "sub2api_api_key": "sub2-key",
        }

        with mock.patch("core.config_store.config_store.get", side_effect=_config_getter(cfg)):
            with mock.patch("platforms.chatgpt.sub2api_upload.upload_to_sub2api", return_value=(True, "ok")) as upload_mock:
                with mock.patch("services.external_sync.persist_sub2api_sync_result") as persist_mock:
                    result = sync_account(account)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Sub2API")
        self.assertTrue(result[0]["ok"])
        upload_mock.assert_called_once()
        persist_mock.assert_called_once_with(account, True, "ok")

    def test_sub2api_disabled_skips_auto_upload_but_keeps_configuration(self):
        account = DummyAccount()
        cfg = {
            "contribution_enabled": "0",
            "sub2api_enabled": "0",
            "sub2api_api_url": "http://sub2api.local",
            "sub2api_api_key": "sub2-key",
        }

        with mock.patch("core.config_store.config_store.get", side_effect=_config_getter(cfg)):
            with mock.patch("platforms.chatgpt.sub2api_upload.upload_to_sub2api") as upload_mock:
                with mock.patch("services.external_sync.persist_sub2api_sync_result") as persist_mock:
                    result = sync_account(account)

        self.assertEqual(result, [])
        upload_mock.assert_not_called()
        persist_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
