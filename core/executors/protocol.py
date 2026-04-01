"""纯协议执行器 - 基于 curl_cffi"""

from curl_cffi import requests as curl_requests
from ..base_executor import BaseExecutor, Response
from ..proxy_utils import build_requests_proxy_config


class ProtocolExecutor(BaseExecutor):
    def __init__(self, proxy: str = None, impersonate: str = "chrome124"):
        super().__init__(proxy)
        self.s = curl_requests.Session()
        self.s.impersonate = impersonate
        if proxy:
            self.s.proxies = build_requests_proxy_config(proxy)
        self.s.headers.update(
            {
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
        )

    def _wrap(self, r) -> Response:
        cookies = {c.name: c.value for c in self.s.cookies.jar}
        return Response(
            status_code=r.status_code,
            text=r.text,
            headers=dict(r.headers),
            cookies=cookies,
        )

    def get(self, url, *, headers=None, params=None) -> Response:
        r = self.s.get(url, headers=headers, params=params)
        return self._wrap(r)

    def post(self, url, *, headers=None, params=None, data=None, json=None) -> Response:
        r = self.s.post(url, headers=headers, params=params, data=data, json=json)
        return self._wrap(r)

    def get_cookies(self) -> dict:
        return {c.name: c.value for c in self.s.cookies.jar}

    def set_cookies(self, cookies: dict) -> None:
        for k, v in cookies.items():
            self.s.cookies.set(k, v)

    def close(self) -> None:
        self.s.close()
