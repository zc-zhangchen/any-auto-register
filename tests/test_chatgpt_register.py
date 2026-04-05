import json
import sys
import types
import unittest
from unittest import mock

smstome_tool_stub = types.ModuleType("smstome_tool")
smstome_tool_stub.PhoneEntry = type("PhoneEntry", (), {})
smstome_tool_stub.get_unused_phone = lambda *args, **kwargs: None
smstome_tool_stub.mark_phone_blacklisted = lambda *args, **kwargs: None
smstome_tool_stub.parse_country_slugs = lambda value: []
smstome_tool_stub.update_global_phone_list = lambda *args, **kwargs: 0
smstome_tool_stub.wait_for_otp = lambda *args, **kwargs: None
sys.modules.setdefault("smstome_tool", smstome_tool_stub)

from platforms.chatgpt.oauth_client import OAuthClient
from platforms.chatgpt.refresh_token_registration_engine import (
    RefreshTokenRegistrationEngine,
)
from platforms.chatgpt.utils import FlowState


class DummyEmailService:
    service_type = type("ST", (), {"value": "dummy"})()

    def create_email(self):
        return {"email": "user@example.com", "service_id": "svc-1"}

    def get_verification_code(self, **kwargs):
        return "123456"


class RefreshTokenRegistrationEngineTests(unittest.TestCase):
    def _make_engine(self, **kwargs):
        return RefreshTokenRegistrationEngine(
            email_service=DummyEmailService(),
            proxy_url="http://127.0.0.1:7890",
            callback_logger=lambda msg: None,
            **kwargs,
        )

    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.OAuthManager")
    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.OAuthClient")
    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.ChatGPTClient")
    def test_run_uses_new_register_then_passwordless_oauth_main_chain(
        self,
        mock_chatgpt_client_cls,
        mock_oauth_client_cls,
        mock_oauth_manager_cls,
    ):
        register_client = mock.Mock()
        register_client.device_id = "device-fixed"
        register_client.ua = "UA"
        register_client.sec_ch_ua = '"Chromium";v="136"'
        register_client.impersonate = "chrome136"
        register_client.register_complete_flow.return_value = (True, "注册成功")
        mock_chatgpt_client_cls.return_value = register_client

        oauth_client = mock.Mock()
        oauth_client.login_and_get_tokens.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "id_token": "id-token",
            "account_id": "acct-1",
        }
        oauth_client.last_workspace_id = "ws-1"
        oauth_client._decode_oauth_session_cookie.return_value = {
            "workspaces": [{"id": "ws-1"}]
        }
        oauth_client._get_cookie_value.return_value = "session-1"
        mock_oauth_client_cls.return_value = oauth_client

        oauth_manager = mock.Mock()
        oauth_manager.extract_account_info.return_value = {
            "email": "user@example.com",
            "account_id": "acct-1",
        }
        mock_oauth_manager_cls.return_value = oauth_manager

        engine = self._make_engine(extra_config={"register_max_retries": 1})
        result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(result.email, "user@example.com")
        self.assertEqual(result.account_id, "acct-1")
        self.assertEqual(result.workspace_id, "ws-1")
        self.assertEqual(result.refresh_token, "rt")
        self.assertEqual(result.session_token, "session-1")
        self.assertEqual(result.source, "register")

        register_client.register_complete_flow.assert_called_once()
        oauth_client.login_and_get_tokens.assert_called_once()
        register_kwargs = register_client.register_complete_flow.call_args.kwargs
        self.assertTrue(register_kwargs["stop_before_about_you_submission"])
        login_kwargs = oauth_client.login_and_get_tokens.call_args.kwargs
        self.assertTrue(login_kwargs["prefer_passwordless_login"])
        self.assertFalse(login_kwargs["allow_phone_verification"])
        self.assertTrue(login_kwargs["complete_about_you_if_needed"])
        self.assertTrue(login_kwargs["force_new_browser"])
        self.assertEqual(login_kwargs["device_id"], "")
        self.assertEqual(login_kwargs["login_source"], "post_register_workspace_recovery")

    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.OAuthManager")
    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.OAuthClient")
    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.ChatGPTClient")
    def test_run_switches_to_login_when_register_flow_reports_existing_account(
        self,
        mock_chatgpt_client_cls,
        mock_oauth_client_cls,
        mock_oauth_manager_cls,
    ):
        register_client = mock.Mock()
        register_client.device_id = "device-fixed"
        register_client.ua = "UA"
        register_client.sec_ch_ua = '"Chromium";v="136"'
        register_client.impersonate = "chrome136"
        register_client.register_complete_flow.return_value = (
            False,
            "创建账号失败: HTTP 400: user_already_exists",
        )
        mock_chatgpt_client_cls.return_value = register_client

        oauth_client = mock.Mock()
        oauth_client.login_and_get_tokens.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "id_token": "id-token",
        }
        oauth_client.last_workspace_id = "ws-1"
        oauth_client._decode_oauth_session_cookie.return_value = {
            "workspaces": [{"id": "ws-1"}]
        }
        oauth_client._get_cookie_value.return_value = ""
        mock_oauth_client_cls.return_value = oauth_client

        oauth_manager = mock.Mock()
        oauth_manager.extract_account_info.return_value = {
            "email": "user@example.com",
            "account_id": "acct-existing",
        }
        mock_oauth_manager_cls.return_value = oauth_manager

        engine = self._make_engine()
        result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(result.source, "login")
        self.assertEqual(result.account_id, "acct-existing")
        login_kwargs = oauth_client.login_and_get_tokens.call_args.kwargs
        self.assertEqual(login_kwargs["login_source"], "existing_account_recovery")

    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.OAuthManager")
    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.OAuthClient")
    @mock.patch("platforms.chatgpt.refresh_token_registration_engine.ChatGPTClient")
    def test_run_disables_full_flow_retry_even_if_max_retries_is_large(
        self,
        mock_chatgpt_client_cls,
        mock_oauth_client_cls,
        mock_oauth_manager_cls,
    ):
        class RotatingEmailService:
            service_type = type("ST", (), {"value": "dummy"})()

            def __init__(self):
                self.index = 0

            def create_email(self):
                self.index += 1
                return {
                    "email": f"user{self.index}@example.com",
                    "service_id": f"svc-{self.index}",
                }

            def get_verification_code(self, **kwargs):
                return "123456"

        register_client = mock.Mock()
        register_client.device_id = "device-fixed"
        register_client.ua = "UA"
        register_client.sec_ch_ua = '"Chromium";v="136"'
        register_client.impersonate = "chrome136"
        register_client.register_complete_flow.side_effect = [
            (False, "network timeout"),
            (True, "注册成功"),
        ]
        mock_chatgpt_client_cls.return_value = register_client

        oauth_client = mock.Mock()
        oauth_client.login_and_get_tokens.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "id_token": "id-token",
            "account_id": "acct-1",
        }
        oauth_client.last_workspace_id = "ws-1"
        oauth_client._decode_oauth_session_cookie.return_value = {
            "workspaces": [{"id": "ws-1"}]
        }
        oauth_client._get_cookie_value.return_value = "session-1"
        mock_oauth_client_cls.return_value = oauth_client

        oauth_manager = mock.Mock()
        oauth_manager.extract_account_info.return_value = {
            "email": "user2@example.com",
            "account_id": "acct-1",
        }
        mock_oauth_manager_cls.return_value = oauth_manager

        engine = RefreshTokenRegistrationEngine(
            email_service=RotatingEmailService(),
            proxy_url="http://127.0.0.1:7890",
            callback_logger=lambda msg: None,
        )
        result = engine.run()

        self.assertFalse(result.success)
        self.assertIn("注册状态机失败", result.error_message)
        call_args = register_client.register_complete_flow.call_args_list
        self.assertEqual(call_args[0].args[0], "user1@example.com")
        self.assertEqual(len(call_args), 1)


class OAuthClientPasswordlessTests(unittest.TestCase):
    def _make_client(self):
        return OAuthClient({}, proxy="http://127.0.0.1:7890", verbose=False)

    def test_login_and_get_tokens_prefers_passwordless_over_password_verify(self):
        client = self._make_client()
        login_password_state = FlowState(
            page_type="login_password",
            continue_url="https://auth.openai.com/log-in/password",
            current_url="https://auth.openai.com/log-in/password",
        )
        email_otp_state = FlowState(
            page_type="email_otp_verification",
            continue_url="https://auth.openai.com/email-verification",
            current_url="https://auth.openai.com/email-verification",
        )
        consent_state = FlowState(
            page_type="consent",
            continue_url="https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
            current_url="https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
        )

        with mock.patch.object(client, "_bootstrap_oauth_session", return_value="https://auth.openai.com/log-in"), \
            mock.patch.object(client, "_submit_authorize_continue", return_value=login_password_state) as submit_continue, \
            mock.patch.object(client, "_send_passwordless_login_otp", return_value=email_otp_state) as send_passwordless, \
            mock.patch.object(client, "_handle_otp_verification", return_value=consent_state), \
            mock.patch.object(client, "_oauth_submit_workspace_and_org", return_value=("auth-code", None)), \
            mock.patch.object(client, "_exchange_code_for_tokens", return_value={"access_token": "at"}), \
            mock.patch.object(client, "_submit_password_verify") as submit_password:
            tokens = client.login_and_get_tokens(
                "user@example.com",
                "Secret123!",
                "device-fixed",
                user_agent="UA",
                sec_ch_ua='"Chromium";v="136"',
                impersonate="chrome136",
                skymail_client=mock.Mock(),
                prefer_passwordless_login=True,
                allow_phone_verification=False,
            )

        self.assertEqual(tokens["access_token"], "at")
        submit_continue.assert_called_once()
        self.assertEqual(submit_continue.call_args.kwargs["screen_hint"], "login")
        send_passwordless.assert_called_once()
        submit_password.assert_not_called()

    def test_build_sentinel_token_for_flow_syncs_device_id_from_token(self):
        client = self._make_client()
        client.device_id = "did-old"
        token = json.dumps(
            {
                "p": "gAAAAAB-test",
                "t": "ok",
                "c": "challenge",
                "id": "did-new",
                "flow": "authorize_continue",
            },
            separators=(",", ":"),
        )

        with mock.patch(
            "platforms.chatgpt.oauth_client.build_sentinel_token",
            return_value=token,
        ):
            result = client._build_sentinel_token_for_flow(
                flow="authorize_continue",
                device_id="did-old",
            )

        self.assertEqual(result, token)
        self.assertEqual(client.device_id, "did-new")

    def test_login_and_get_tokens_visits_add_phone_continue_url_before_phone_branch(self):
        client = self._make_client()
        add_phone_state = FlowState(
            page_type="add_phone",
            continue_url="https://auth.openai.com/add-phone",
            current_url="https://auth.openai.com/api/accounts/email-otp/validate",
            source="api",
        )
        consent_state = FlowState(
            page_type="consent",
            continue_url="https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
            current_url="https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
        )

        with mock.patch.object(client, "_bootstrap_oauth_session", return_value="https://auth.openai.com/log-in"), \
            mock.patch.object(client, "_submit_authorize_continue", return_value=add_phone_state), \
            mock.patch.object(client, "_follow_flow_state", return_value=(None, consent_state)) as follow_state, \
            mock.patch.object(client, "_oauth_submit_workspace_and_org", return_value=("auth-code", None)), \
            mock.patch.object(client, "_exchange_code_for_tokens", return_value={"access_token": "at"}), \
            mock.patch.object(client, "_handle_add_phone_verification") as handle_phone:
            tokens = client.login_and_get_tokens(
                "user@example.com",
                "Secret123!",
                "device-fixed",
                prefer_passwordless_login=True,
                allow_phone_verification=False,
            )

        self.assertEqual(tokens["access_token"], "at")
        follow_state.assert_called_once()
        handle_phone.assert_not_called()

    def test_login_and_get_tokens_uses_canonical_consent_url_when_state_is_add_phone(self):
        client = self._make_client()
        add_phone_state = FlowState(
            page_type="add_phone",
            continue_url="https://auth.openai.com/add-phone",
            current_url="https://auth.openai.com/add-phone",
        )

        with mock.patch.object(client, "_bootstrap_oauth_session", return_value="https://auth.openai.com/log-in"), \
            mock.patch.object(client, "_submit_authorize_continue", return_value=add_phone_state), \
            mock.patch.object(client, "_state_supports_workspace_resolution", return_value=True), \
            mock.patch.object(client, "_state_requires_navigation", return_value=False), \
            mock.patch.object(client, "_oauth_submit_workspace_and_org", return_value=("auth-code", None)) as submit_workspace, \
            mock.patch.object(client, "_exchange_code_for_tokens", return_value={"access_token": "at"}):
            tokens = client.login_and_get_tokens(
                "user@example.com",
                "Secret123!",
                "device-fixed",
                prefer_passwordless_login=True,
                allow_phone_verification=False,
                skymail_client=mock.Mock(),
            )

        self.assertEqual(tokens["access_token"], "at")
        self.assertEqual(
            submit_workspace.call_args.args[0],
            "https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
        )

    def test_login_and_get_tokens_fails_fast_when_add_phone_has_no_workspace(self):
        client = self._make_client()
        add_phone_state = FlowState(
            page_type="add_phone",
            continue_url="https://auth.openai.com/add-phone",
            current_url="https://auth.openai.com/add-phone",
        )

        with mock.patch.object(client, "_bootstrap_oauth_session", return_value="https://auth.openai.com/log-in") as bootstrap, \
            mock.patch.object(client, "_submit_authorize_continue", return_value=add_phone_state) as submit_continue, \
            mock.patch.object(client, "_state_supports_workspace_resolution", return_value=False), \
            mock.patch.object(client, "_state_requires_navigation", return_value=False):
            tokens = client.login_and_get_tokens(
                "user@example.com",
                "Secret123!",
                "device-fixed",
                prefer_passwordless_login=True,
                allow_phone_verification=False,
                skymail_client=mock.Mock(),
            )

        self.assertIsNone(tokens)
        self.assertEqual(bootstrap.call_count, 1)
        self.assertEqual(submit_continue.call_count, 1)
        self.assertIn("未获取到 workspace / callback", client.last_error)

    def test_send_passwordless_login_otp_does_not_send_email_field(self):
        client = self._make_client()
        response = mock.Mock()
        response.status_code = 200
        response.url = "https://auth.openai.com/api/accounts/passwordless/send-otp"
        response.json.return_value = {"page": {"type": "email_otp_verification"}}
        client.session.post = mock.Mock(return_value=response)

        expected_state = FlowState(
            page_type="email_otp_verification",
            continue_url="https://auth.openai.com/email-verification",
            current_url="https://auth.openai.com/email-verification",
        )
        with mock.patch.object(
            client,
            "_state_from_payload",
            return_value=expected_state,
        ):
            state = client._send_passwordless_login_otp(
                "user@example.com",
                "device-fixed",
            )

        self.assertEqual(state, expected_state)
        kwargs = client.session.post.call_args.kwargs
        self.assertNotIn("json", kwargs)
        self.assertNotIn("data", kwargs)

    def test_login_and_get_tokens_submits_about_you_when_configured(self):
        client = self._make_client()
        about_you_state = FlowState(
            page_type="about_you",
            continue_url="https://auth.openai.com/about-you",
            current_url="https://auth.openai.com/about-you",
        )
        consent_state = FlowState(
            page_type="consent",
            continue_url="https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
            current_url="https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
        )

        with mock.patch.object(client, "_bootstrap_oauth_session", return_value="https://auth.openai.com/log-in"), \
            mock.patch.object(client, "_submit_authorize_continue", return_value=about_you_state), \
            mock.patch.object(client, "_submit_about_you_create_account", return_value=consent_state) as submit_about_you, \
            mock.patch.object(client, "_oauth_submit_workspace_and_org", return_value=("auth-code", None)), \
            mock.patch.object(client, "_exchange_code_for_tokens", return_value={"access_token": "at"}):
            tokens = client.login_and_get_tokens(
                "user@example.com",
                "Secret123!",
                "device-fixed",
                prefer_passwordless_login=True,
                allow_phone_verification=False,
                complete_about_you_if_needed=True,
                first_name="Ivy",
                last_name="Stone",
                birthdate="1990-01-02",
                skymail_client=mock.Mock(),
            )

        self.assertEqual(tokens["access_token"], "at")
        submit_about_you.assert_called_once()
        self.assertEqual(submit_about_you.call_args.args[0], "Ivy")
        self.assertEqual(submit_about_you.call_args.args[1], "Stone")
        self.assertEqual(submit_about_you.call_args.args[2], "1990-01-02")


if __name__ == "__main__":
    unittest.main()
