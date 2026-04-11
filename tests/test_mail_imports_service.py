import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_microsoft_import_rules_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "mail_imports"
        / "microsoft_import_rules.py"
    )
    spec = importlib.util.spec_from_file_location("test_microsoft_import_rules", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MailImportServiceTests(unittest.TestCase):
    def test_parse_microsoft_import_record_requires_oauth_fields(self):
        rules_module = load_microsoft_import_rules_module()
        parse_microsoft_import_record = rules_module.parse_microsoft_import_record

        with self.assertRaisesRegex(ValueError, "缺少 client_id 或 refresh_token"):
            parse_microsoft_import_record(1, "demo@outlook.com----password")

    def test_parse_microsoft_import_line_supports_mailapi_url(self):
        rules_module = load_microsoft_import_rules_module()
        parse_microsoft_import_line = rules_module.parse_microsoft_import_line

        record = parse_microsoft_import_line(
            1,
            "demo@outlook.com----https://mailapi.icu/key?type=html&orderNo=abc123",
        )

        self.assertEqual(record.email, "demo@outlook.com")
        self.assertEqual(record.account_type, "mailapi_url")
        self.assertEqual(record.mailapi_url, "https://mailapi.icu/key?type=html&orderNo=abc123")

    def test_rule_engine_returns_first_failure(self):
        rules_module = load_microsoft_import_rules_module()
        MicrosoftMailImportRecord = rules_module.MicrosoftMailImportRecord
        MicrosoftMailImportRuleEngine = rules_module.MicrosoftMailImportRuleEngine

        calls = []

        class FirstRejectRule:
            def evaluate(self, record, context):
                calls.append("first")
                return {"ok": False, "message": f"reject:{record.email}"}

        class SecondRuleMustNotRun:
            def evaluate(self, record, context):
                calls.append("second")
                raise AssertionError("second rule should not be executed after first failure")

        engine = MicrosoftMailImportRuleEngine([FirstRejectRule(), SecondRuleMustNotRun()])
        record = MicrosoftMailImportRecord(
            line_number=1,
            email="demo@outlook.com",
            password="password",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        result = engine.evaluate(record, {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "reject:demo@outlook.com")
        self.assertEqual(calls, ["first"])

    def test_duplicate_email_rule_rejects_existing_account(self):
        rules_module = load_microsoft_import_rules_module()
        DuplicateMicrosoftMailboxRule = rules_module.DuplicateMicrosoftMailboxRule
        MicrosoftMailImportRecord = rules_module.MicrosoftMailImportRecord

        rule = DuplicateMicrosoftMailboxRule()
        record = MicrosoftMailImportRecord(
            line_number=2,
            email="demo@outlook.com",
            password="password",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        result = rule.evaluate(record, {"existing_emails": {"demo@outlook.com"}})
        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "行 2: 邮箱已存在: demo@outlook.com")

    def test_microsoft_mailbox_availability_rule_rejects_service_abuse_mode(self):
        rules_module = load_microsoft_import_rules_module()
        MicrosoftMailImportRecord = rules_module.MicrosoftMailImportRecord
        MicrosoftMailboxAvailabilityRule = rules_module.MicrosoftMailboxAvailabilityRule

        class FakeMailbox:
            def probe_oauth_availability(self, **kwargs):
                return {
                    "ok": False,
                    "reason": "service_abuse_mode",
                    "message": "微软邮箱可用性检测未通过，账号处于 service abuse mode",
                }

        rule = MicrosoftMailboxAvailabilityRule(FakeMailbox())
        record = MicrosoftMailImportRecord(
            line_number=5,
            email="demo@hotmail.com",
            password="password",
            client_id="client-id",
            refresh_token="refresh-token",
        )

        result = rule.evaluate(record, {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "行 5: 微软邮箱可用性检测未通过，账号处于 service abuse mode")

    def test_applemail_strategy_saves_pool_and_returns_snapshot(self):
        from services.mail_imports.providers import AppleMailImportStrategy
        from services.mail_imports.schemas import MailImportExecuteRequest

        strategy = AppleMailImportStrategy()
        with tempfile.TemporaryDirectory() as tmp_dir:
            previous_cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                response = strategy.execute(
                    MailImportExecuteRequest(
                        type="applemail",
                        content="demo@example.com----password----client-id----refresh-token",
                        pool_dir="mail",
                        filename="applemail_demo.json",
                        bind_to_config=False,
                    )
                )
            finally:
                os.chdir(previous_cwd)

            saved_path = Path(tmp_dir) / "mail" / "applemail_demo.json"
            self.assertTrue(saved_path.exists())
            self.assertEqual(response.summary.total, 1)
            self.assertEqual(response.summary.success, 1)
            self.assertEqual(response.summary.failed, 0)
            self.assertEqual(response.snapshot.filename, "applemail_demo.json")
            self.assertEqual(response.snapshot.pool_dir, "mail")
            self.assertEqual(response.snapshot.count, 1)
            self.assertEqual(response.snapshot.items[0].email, "demo@example.com")

    def test_microsoft_strategy_rejects_invalid_mailapi_url(self):
        from services.mail_imports.providers import MicrosoftMailImportStrategy
        from services.mail_imports.schemas import MailImportExecuteRequest

        strategy = MicrosoftMailImportStrategy()
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'mail-imports.db'}")
            SQLModel.metadata.create_all(test_engine)

            try:
                with patch("services.mail_imports.providers.engine", test_engine):
                    response = strategy.execute(
                        MailImportExecuteRequest(
                            type="microsoft",
                            content="demo@outlook.com----not-a-url",
                        )
                    )

                    self.assertEqual(response.summary.total, 1)
                    self.assertEqual(response.summary.success, 0)
                    self.assertEqual(response.summary.failed, 1)
                    self.assertIn("无效的 mailapi_url", response.errors[0])
                    self.assertEqual(response.snapshot.count, 0)
            finally:
                test_engine.dispose()

    def test_microsoft_strategy_imports_only_rows_that_pass_rules(self):
        from services.mail_imports.schemas import MailImportExecuteRequest
        from services.mail_imports.providers import MicrosoftMailImportStrategy

        strategy = MicrosoftMailImportStrategy()
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'mail-imports.db'}")
            SQLModel.metadata.create_all(test_engine)

            try:
                with patch("services.mail_imports.providers.engine", test_engine), \
                     patch("services.mail_imports.providers.OutlookMailbox") as mailbox_cls:
                    mailbox = mailbox_cls.return_value
                    mailbox.probe_oauth_availability.side_effect = [
                        {"ok": True, "reason": "ok", "message": "微软邮箱可用性检测通过", "access_token": "token-a"},
                        {"ok": False, "reason": "service_abuse_mode", "message": "微软邮箱可用性检测未通过，账号处于 service abuse mode"},
                    ]

                    response = strategy.execute(
                        MailImportExecuteRequest(
                            type="microsoft",
                            content=(
                                "first@outlook.com----password----client-a----refresh-a\n"
                                "second@hotmail.com----password----client-b----refresh-b"
                            ),
                        )
                    )

                    self.assertEqual(response.summary.total, 2)
                    self.assertEqual(response.summary.success, 1)
                    self.assertEqual(response.summary.failed, 1)
                    self.assertEqual(response.snapshot.count, 1)
                    self.assertEqual(response.snapshot.items[0].email, "first@outlook.com")
                    self.assertIn("service abuse mode", response.errors[0])
            finally:
                test_engine.dispose()

    def test_microsoft_strategy_supports_mixed_oauth_and_mailapi_rows(self):
        from services.mail_imports.schemas import MailImportExecuteRequest
        from services.mail_imports.providers import MicrosoftMailImportStrategy

        strategy = MicrosoftMailImportStrategy()
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'mail-imports.db'}")
            SQLModel.metadata.create_all(test_engine)

            try:
                with patch("services.mail_imports.providers.engine", test_engine), \
                     patch("services.mail_imports.providers.OutlookMailbox") as mailbox_cls:
                    mailbox = mailbox_cls.return_value
                    mailbox.probe_oauth_availability.return_value = {
                        "ok": True,
                        "reason": "ok",
                        "message": "微软邮箱可用性检测通过",
                        "access_token": "token-a",
                    }

                    response = strategy.execute(
                        MailImportExecuteRequest(
                            type="microsoft",
                            content=(
                                "oauth@outlook.com----password----client-a----refresh-a\n"
                                "mailapi@hotmail.com----https://mailapi.icu/key?type=html&orderNo=abc123"
                            ),
                        )
                    )

                    self.assertEqual(response.summary.total, 2)
                    self.assertEqual(response.summary.success, 2)
                    self.assertEqual(response.summary.failed, 0)
                    self.assertEqual(response.snapshot.count, 2)
                    account_types = {item.email: item.account_type for item in response.snapshot.items}
                    self.assertEqual(account_types.get("oauth@outlook.com"), "microsoft_oauth")
                    self.assertEqual(account_types.get("mailapi@hotmail.com"), "mailapi_url")
            finally:
                test_engine.dispose()

    def test_microsoft_strategy_alias_split_generates_alias_emails(self):
        from services.mail_imports.schemas import MailImportExecuteRequest
        from services.mail_imports.providers import MicrosoftMailImportStrategy

        strategy = MicrosoftMailImportStrategy()
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'mail-imports.db'}")
            SQLModel.metadata.create_all(test_engine)

            try:
                with patch("services.mail_imports.providers.engine", test_engine), \
                     patch("services.mail_imports.providers.OutlookMailbox") as mailbox_cls, \
                     patch("services.mail_imports.providers.random.choices") as mock_choices:
                    mailbox = mailbox_cls.return_value
                    mailbox.probe_oauth_availability.return_value = {
                        "ok": True,
                        "reason": "ok",
                        "message": "微软邮箱可用性检测通过",
                        "access_token": "token-a",
                    }
                    mock_choices.side_effect = [
                        list("abcdef"),
                        list("ghijkl"),
                    ]

                    response = strategy.execute(
                        MailImportExecuteRequest(
                            type="microsoft",
                            content="alias@outlook.com----password----client-a----refresh-a",
                            alias_split_enabled=True,
                            alias_split_count=2,
                            alias_include_original=False,
                        )
                    )

                    self.assertEqual(response.summary.total, 2)
                    self.assertEqual(response.summary.success, 2)
                    self.assertEqual(response.summary.failed, 0)
                    imported_emails = sorted(item.email for item in response.snapshot.items)
                    self.assertEqual(
                        imported_emails,
                        sorted(
                            [
                                "alias+abcdef@outlook.com",
                                "alias+ghijkl@outlook.com",
                            ]
                        ),
                    )
            finally:
                test_engine.dispose()


if __name__ == "__main__":
    unittest.main()
