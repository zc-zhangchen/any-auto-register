import unittest

from core.task_runtime import (
    PauseTaskRequested,
    RegisterTaskControl,
    RegisterTaskStore,
    SkipCurrentAttemptRequested,
    StopTaskRequested,
)


class RegisterTaskControlTests(unittest.TestCase):
    def test_skip_request_is_consumed_only_once(self):
        control = RegisterTaskControl()

        control.request_skip_current()

        with self.assertRaises(SkipCurrentAttemptRequested):
            control.checkpoint()

        control.checkpoint()

    def test_stop_request_is_sticky(self):
        control = RegisterTaskControl()

        control.request_stop()

        with self.assertRaises(StopTaskRequested):
            control.checkpoint()
        with self.assertRaises(StopTaskRequested):
            control.checkpoint()

    def test_pause_request_is_sticky_and_preserves_reason(self):
        control = RegisterTaskControl()

        first_request = control.request_pause("疑似风控")
        second_request = control.request_pause("另一个原因")

        self.assertTrue(first_request)
        self.assertFalse(second_request)
        self.assertTrue(control.is_pause_requested())

        with self.assertRaises(PauseTaskRequested) as exc_info:
            control.checkpoint()
        self.assertIn("疑似风控", str(exc_info.exception))

    def test_skip_current_targets_only_active_attempts_in_multithread_mode(self):
        control = RegisterTaskControl()
        attempt_a = control.start_attempt()
        attempt_b = control.start_attempt()

        control.request_skip_current()

        with self.assertRaises(SkipCurrentAttemptRequested):
            control.checkpoint(attempt_id=attempt_a)
        with self.assertRaises(SkipCurrentAttemptRequested):
            control.checkpoint(attempt_id=attempt_b)

        control.finish_attempt(attempt_a)
        control.finish_attempt(attempt_b)

        attempt_c = control.start_attempt()
        control.checkpoint(attempt_id=attempt_c)
        control.finish_attempt(attempt_c)


class RegisterTaskStoreTests(unittest.TestCase):
    def test_snapshot_contains_control_and_skip_fields(self):
        store = RegisterTaskStore()
        task_id = "task-runtime-snapshot"

        store.create(
            task_id,
            platform="chatgpt",
            total=2,
            source="manual",
            meta={"scope": "unit"},
        )
        store.request_skip_current(task_id)
        store.finish(
            task_id,
            status="done",
            success=1,
            skipped=1,
            errors=["error-a"],
        )

        snapshot = store.snapshot(task_id)

        self.assertEqual(snapshot["success"], 1)
        self.assertEqual(snapshot["skipped"], 1)
        self.assertEqual(snapshot["errors"], ["error-a"])
        self.assertEqual(
            snapshot["control"]["pending_skip_requests"],
            1,
        )

    def test_snapshot_contains_pause_fields(self):
        store = RegisterTaskStore()
        task_id = "task-runtime-pause"

        store.create(
            task_id,
            platform="chatgpt",
            total=1,
            source="manual",
        )
        control_snapshot = store.request_pause(task_id, "检测到 HTTP 400，疑似风控")
        store.finish(
            task_id,
            status="paused",
            success=0,
            skipped=0,
            errors=["注册失败: 400 - rate limited"],
            error="检测到 HTTP 400，疑似风控",
        )

        snapshot = store.snapshot(task_id)

        self.assertTrue(control_snapshot["pause_requested"])
        self.assertEqual(
            control_snapshot["pause_reason"],
            "检测到 HTTP 400，疑似风控",
        )
        self.assertEqual(snapshot["status"], "paused")
        self.assertTrue(snapshot["control"]["pause_requested"])
        self.assertEqual(
            snapshot["control"]["pause_reason"],
            "检测到 HTTP 400，疑似风控",
        )


if __name__ == "__main__":
    unittest.main()
