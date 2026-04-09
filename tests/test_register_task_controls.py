import io
import sys
import threading
import time
import unittest
from unittest.mock import patch

from api.tasks import RegisterTaskRequest, _create_task_record, _run_register, _task_store
from core.base_mailbox import BaseMailbox, MailboxAccount
from core.base_platform import Account, BasePlatform


class _FakeMailbox(BaseMailbox):
    def get_email(self) -> MailboxAccount:
        return MailboxAccount(email="demo@example.com")

    def get_current_ids(self, account: MailboxAccount) -> set:
        return set()

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        def poll_once():
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=0.01,
            poll_once=poll_once,
        )


class _FakePlatform(BasePlatform):
    name = "fake"
    display_name = "Fake"

    def __init__(self, config=None, mailbox=None):
        super().__init__(config)
        self.mailbox = mailbox

    def register(self, email: str, password: str = None) -> Account:
        account = self.mailbox.get_email()
        self.mailbox.wait_for_code(account, timeout=1)
        return Account(
            platform="fake",
            email=account.email,
            password=password or "pw",
        )

    def check_valid(self, account: Account) -> bool:
        return True


class _EmojiLoggingPlatform(BasePlatform):
    name = "fake"
    display_name = "Fake"

    def __init__(self, config=None, mailbox=None):
        super().__init__(config)
        self.mailbox = mailbox

    def register(self, email: str, password: str = None) -> Account:
        if self._log_fn:
            self._log_fn("\u2705 OAuth 注册成功")
        return Account(
            platform="fake",
            email="emoji@example.com",
            password=password or "pw",
        )

    def check_valid(self, account: Account) -> bool:
        return True


class _FakeChatGPTWorkspacePlatform(BasePlatform):
    name = "chatgpt"
    display_name = "ChatGPT"

    _counter = 0

    def __init__(self, config=None, mailbox=None):
        super().__init__(config)
        self.mailbox = mailbox

    @classmethod
    def reset_counter(cls):
        cls._counter = 0

    def register(self, email: str, password: str = None) -> Account:
        type(self)._counter += 1
        index = type(self)._counter
        return Account(
            platform="chatgpt",
            email=f"user{index}@example.com",
            password=password or "pw",
            extra={"workspace_id": f"ws-{index}"},
        )

    def check_valid(self, account: Account) -> bool:
        return True


class _AutoPause400Platform(BasePlatform):
    name = "fake"
    display_name = "Fake"

    _counter = 0
    _counter_lock = threading.Lock()

    def __init__(self, config=None, mailbox=None):
        super().__init__(config)
        self.mailbox = mailbox

    @classmethod
    def reset_counter(cls):
        with cls._counter_lock:
            cls._counter = 0

    def register(self, email: str, password: str = None) -> Account:
        with type(self)._counter_lock:
            type(self)._counter += 1
            current = type(self)._counter

        if current == 1:
            time.sleep(0.05)
            raise RuntimeError("注册失败: 400 - rate limited")

        deadline = time.time() + 2
        while time.time() < deadline:
            self._task_control.checkpoint()
            time.sleep(0.01)

        return Account(
            platform="fake",
            email="should-not-complete@example.com",
            password=password or "pw",
        )

    def check_valid(self, account: Account) -> bool:
        return True


class _FailingGbkStdout(io.TextIOBase):
    encoding = "gbk"

    def __init__(self):
        super().__init__()
        self.buffer = io.BytesIO()

    def write(self, text):
        payload = str(text)
        encoded = payload.encode(self.encoding)
        self.buffer.write(encoded)
        return len(payload)

    def flush(self):
        return None


class RegisterTaskControlFlowTests(unittest.TestCase):
    def _build_request(self, **overrides):
        payload = {
            "platform": "fake",
            "count": 1,
            "concurrency": 1,
            "proxy": "http://proxy.local:8080",
            "extra": {"mail_provider": "fake"},
        }
        payload.update(overrides)
        return RegisterTaskRequest(**payload)

    def _run_with_control(self, task_id: str, *, stop: bool = False, skip: bool = False):
        req = self._build_request()
        _create_task_record(task_id, req, "manual", None)
        if stop:
            _task_store.request_stop(task_id)
        if skip:
            _task_store.request_skip_current(task_id)

        with (
            patch("core.registry.get", return_value=_FakePlatform),
            patch("core.base_mailbox.create_mailbox", return_value=_FakeMailbox()),
            patch("core.db.save_account", side_effect=lambda account: account),
            patch("api.tasks._save_task_log"),
        ):
            _run_register(task_id, req)

        return _task_store.snapshot(task_id)

    def test_skip_current_marks_attempt_as_skipped(self):
        snapshot = self._run_with_control("task-control-skip", skip=True)

        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["success"], 0)
        self.assertEqual(snapshot["skipped"], 1)
        self.assertEqual(snapshot["errors"], [])

    def test_stop_marks_task_as_stopped(self):
        snapshot = self._run_with_control("task-control-stop", stop=True)

        self.assertEqual(snapshot["status"], "stopped")
        self.assertEqual(snapshot["success"], 0)
        self.assertEqual(snapshot["skipped"], 0)
        self.assertEqual(snapshot["errors"], [])

    def test_chatgpt_logs_workspace_progress_after_each_success(self):
        task_id = "task-chatgpt-workspace-progress"
        req = self._build_request(platform="chatgpt", count=2, concurrency=1)
        _create_task_record(task_id, req, "manual", None)
        _FakeChatGPTWorkspacePlatform.reset_counter()

        with (
            patch("core.registry.get", return_value=_FakeChatGPTWorkspacePlatform),
            patch("core.base_mailbox.create_mailbox", return_value=_FakeMailbox()),
            patch("core.db.save_account", side_effect=lambda account: account),
            patch("api.tasks._save_task_log"),
        ):
            _run_register(task_id, req)

        snapshot = _task_store.snapshot(task_id)
        joined_logs = "\n".join(snapshot["logs"])

        self.assertIn("workspace进度: 1/2", joined_logs)
        self.assertIn("workspace进度: 2/2", joined_logs)


    def test_emoji_log_does_not_turn_success_into_failure_under_gbk_stdout(self):
        task_id = "task-gbk-emoji-log"
        req = self._build_request()
        _create_task_record(task_id, req, "manual", None)
        fake_stdout = _FailingGbkStdout()

        with (
            patch("core.registry.get", return_value=_EmojiLoggingPlatform),
            patch("core.base_mailbox.create_mailbox", return_value=_FakeMailbox()),
            patch("core.db.save_account", side_effect=lambda account: account),
            patch("api.tasks._save_task_log"),
            patch.object(sys, "stdout", fake_stdout),
        ):
            _run_register(task_id, req)

        snapshot = _task_store.snapshot(task_id)
        joined_logs = "\n".join(snapshot["logs"])

        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["success"], 1)
        self.assertIn("\u2705 OAuth 注册成功", joined_logs)

    def test_http_400_auto_pauses_entire_task_and_logs_risk_message(self):
        task_id = "task-auto-pause-http-400"
        req = self._build_request(count=2, concurrency=2)
        _create_task_record(task_id, req, "manual", None)
        _AutoPause400Platform.reset_counter()

        with (
            patch("core.registry.get", return_value=_AutoPause400Platform),
            patch("core.base_mailbox.create_mailbox", return_value=_FakeMailbox()),
            patch("core.db.save_account", side_effect=lambda account: account),
            patch("api.tasks._save_task_log"),
        ):
            _run_register(task_id, req)

        snapshot = _task_store.snapshot(task_id)
        joined_logs = "\n".join(snapshot["logs"])

        self.assertEqual(snapshot["status"], "paused")
        self.assertEqual(snapshot["success"], 0)
        self.assertEqual(snapshot["skipped"], 0)
        self.assertEqual(len(snapshot["errors"]), 1)
        self.assertIn("400", snapshot["errors"][0])
        self.assertTrue(snapshot["control"]["pause_requested"])
        self.assertIn("可能触发风控", snapshot["control"]["pause_reason"])
        self.assertIn("可能触发风控", joined_logs)

    def test_http_400_auto_pause_can_be_disabled_for_register_task(self):
        task_id = "task-auto-pause-http-400-disabled"
        req = self._build_request(
            count=2,
            concurrency=2,
            auto_pause_on_http_400=False,
        )
        _create_task_record(task_id, req, "manual", None)
        _AutoPause400Platform.reset_counter()

        with (
            patch("core.registry.get", return_value=_AutoPause400Platform),
            patch("core.base_mailbox.create_mailbox", return_value=_FakeMailbox()),
            patch("core.db.save_account", side_effect=lambda account: account),
            patch("api.tasks._save_task_log"),
        ):
            _run_register(task_id, req)

        snapshot = _task_store.snapshot(task_id)
        joined_logs = "\n".join(snapshot["logs"])

        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["success"], 1)
        self.assertEqual(snapshot["skipped"], 0)
        self.assertEqual(len(snapshot["errors"]), 1)
        self.assertFalse(snapshot["control"]["pause_requested"])
        self.assertNotIn("[PAUSE]", joined_logs)


if __name__ == "__main__":
    unittest.main()
