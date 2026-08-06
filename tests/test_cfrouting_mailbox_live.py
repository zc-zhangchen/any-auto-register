import os
import time
import unittest

from core.base_mailbox import MailboxAccount, create_mailbox


def _get_env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _env_enabled(name: str) -> bool:
    return _get_env(name).lower() in {"1", "true", "yes", "on"}


class CFRoutingMailboxLiveTests(unittest.TestCase):
    """真实 IMAP 集成测试。

    用法：
    1. 设置 `CFROUTING_LIVE_ENABLE=1`
    2. 配置真实的 IMAP/邮件路由环境变量
    3. 运行本测试后，复制打印出的 alias，手动触发一封验证码邮件发送到该地址
    4. 若希望断言“抓到的就是指定真实值”，再设置 `CFROUTING_LIVE_EXPECTED_CODE`
    5. 若希望把“你手动发信的时间”排除在计时外，设置 `CFROUTING_LIVE_PROMPT_AFTER_SEND=1`

    常见配置：
    - QQ: `CFROUTING_LIVE_IMAP_SERVER=imap.qq.com`
    - 个人 Gmail: `CFROUTING_LIVE_IMAP_SERVER=imap.gmail.com`
    """

    REQUIRED_ENV_VARS = (
        "CFROUTING_LIVE_DOMAIN",
        "CFROUTING_LIVE_IMAP_SERVER",
        "CFROUTING_LIVE_USERNAME",
        "CFROUTING_LIVE_PASSWORD",
    )

    def _ensure_live_env(self) -> None:
        if not _env_enabled("CFROUTING_LIVE_ENABLE"):
            self.skipTest("未启用真实 CFRouting 集成测试；设置 CFROUTING_LIVE_ENABLE=1 后再运行")

        missing = [name for name in self.REQUIRED_ENV_VARS if not _get_env(name)]
        if missing:
            self.skipTest(f"缺少环境变量: {', '.join(missing)}")

    def _build_mailbox(self):
        config = {
            "cfrouting_domain": _get_env("CFROUTING_LIVE_DOMAIN"),
            "cfrouting_imap_server": _get_env("CFROUTING_LIVE_IMAP_SERVER"),
            "cfrouting_imap_port": _get_env("CFROUTING_LIVE_IMAP_PORT", "993"),
            "cfrouting_username": _get_env("CFROUTING_LIVE_USERNAME"),
            "cfrouting_password": _get_env("CFROUTING_LIVE_PASSWORD"),
            "cfrouting_mailboxes": _get_env("CFROUTING_LIVE_MAILBOXES", "INBOX"),
            "cfrouting_poll_interval_seconds": _get_env(
                "CFROUTING_LIVE_POLL_INTERVAL",
                "2",
            ),
        }
        return create_mailbox("cfrouting", extra=config)

    def _build_account(self, mailbox) -> MailboxAccount:
        fixed_alias = _get_env("CFROUTING_LIVE_FIXED_ALIAS")
        if fixed_alias:
            return MailboxAccount(email=fixed_alias, account_id=fixed_alias)
        return mailbox.get_email()

    def test_wait_for_code_can_capture_real_verification_email(self):
        self._ensure_live_env()

        mailbox = self._build_mailbox()
        mailbox._log_fn = lambda message: print(
            f"[CFRouting Live] {message}",
            flush=True,
        )
        account = self._build_account(mailbox)
        timeout = int(_get_env("CFROUTING_LIVE_TIMEOUT", "180"))
        keyword = _get_env("CFROUTING_LIVE_KEYWORD")
        code_pattern = _get_env("CFROUTING_LIVE_CODE_PATTERN") or None
        expected_code = _get_env("CFROUTING_LIVE_EXPECTED_CODE")
        poll_interval = _get_env("CFROUTING_LIVE_POLL_INTERVAL", "2")

        before_ids = mailbox.get_current_ids(account)
        print(
            f"\n[CFRouting Live] alias={account.email}\n"
            f"[CFRouting Live] mailboxes={_get_env('CFROUTING_LIVE_MAILBOXES', 'INBOX')}\n"
            f"[CFRouting Live] poll_interval={poll_interval}s\n"
            f"[CFRouting Live] timeout={timeout}s\n"
            "[CFRouting Live] 现在请触发验证码邮件发送到上面的 alias。\n",
            flush=True,
        )
        if _env_enabled("CFROUTING_LIVE_PROMPT_AFTER_SEND"):
            input(
                "[CFRouting Live] 发完验证码邮件后按 Enter，"
                "再开始统计脚本抓码耗时..."
            )
        else:
            print(
                "[CFRouting Live] 测试已开始等待抓码；当前耗时包含你手动发信的时间。\n",
                flush=True,
            )
        wait_started_at = time.monotonic()

        code = mailbox.wait_for_code(
            account,
            keyword=keyword,
            timeout=timeout,
            before_ids=before_ids,
            code_pattern=code_pattern,
        )

        elapsed = time.monotonic() - wait_started_at
        print(
            f"[CFRouting Live] 抓到验证码: {code} "
            f"(等待耗时 {elapsed:.1f}s)",
            flush=True,
        )
        self.assertTrue(str(code or "").strip(), "未抓到有效验证码")
        if expected_code:
            self.assertEqual(
                code,
                expected_code,
                "抓到的验证码与 CFROUTING_LIVE_EXPECTED_CODE 不一致",
            )


if __name__ == "__main__":
    unittest.main()
