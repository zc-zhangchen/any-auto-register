import unittest
from types import SimpleNamespace
from unittest import mock

from core.proxy_pool import ProxyPool


class _FakeExecResult:
    def __init__(self, proxy):
        self._proxy = proxy

    def first(self):
        return self._proxy


class _FakeSession:
    def __init__(self, proxy):
        self._proxy = proxy
        self.added = None
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def exec(self, _query):
        return _FakeExecResult(self._proxy)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True


class ProxyPoolTests(unittest.TestCase):
    def test_report_fail_auto_disables_proxy_when_enabled(self):
        proxy = SimpleNamespace(
            url="http://proxy.local:8080",
            success_count=0,
            fail_count=4,
            is_active=True,
            last_checked=None,
        )
        fake_session = _FakeSession(proxy)

        with (
            mock.patch("core.proxy_pool.Session", return_value=fake_session),
            mock.patch("core.proxy_pool.config_store.get", return_value="1"),
        ):
            ProxyPool().report_fail(proxy.url)

        self.assertEqual(proxy.fail_count, 5)
        self.assertFalse(proxy.is_active)
        self.assertIsNotNone(proxy.last_checked)
        self.assertIs(fake_session.added, proxy)
        self.assertTrue(fake_session.committed)

    def test_report_fail_does_not_disable_proxy_when_switch_is_off(self):
        proxy = SimpleNamespace(
            url="http://proxy.local:8080",
            success_count=0,
            fail_count=4,
            is_active=True,
            last_checked=None,
        )
        fake_session = _FakeSession(proxy)

        with (
            mock.patch("core.proxy_pool.Session", return_value=fake_session),
            mock.patch("core.proxy_pool.config_store.get", return_value="0"),
        ):
            ProxyPool().report_fail(proxy.url)

        self.assertEqual(proxy.fail_count, 5)
        self.assertTrue(proxy.is_active)
        self.assertIsNotNone(proxy.last_checked)
        self.assertIs(fake_session.added, proxy)
        self.assertTrue(fake_session.committed)


if __name__ == "__main__":
    unittest.main()
