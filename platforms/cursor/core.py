"""Cursor 注册协议核心实现"""

import re, uuid, json, urllib.parse, random, string
from typing import Optional, Callable
from core.proxy_utils import build_requests_proxy_config

AUTH = "https://authenticator.cursor.sh"
CURSOR = "https://cursor.com"

ACTION_SUBMIT_EMAIL = "d0b05a2a36fbe69091c2f49016138171d5c1e4cd"
ACTION_SUBMIT_PASSWORD = "fef846a39073c935bea71b63308b177b113269b7"
ACTION_MAGIC_CODE = "f9e8ae3d58a7cd11cccbcdbf210e6f2a6a2550dd"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

TURNSTILE_SITEKEY = "0x4AAAAAAAMNIvC45A4Wjjln"


def _rand_password(n=16):
    chars = string.ascii_letters + string.digits + "!@#$"
    return "".join(random.choices(chars, k=n))


def _boundary():
    return "----WebKitFormBoundary" + "".join(
        random.choices(string.ascii_letters + string.digits, k=16)
    )


def _multipart(fields: dict, boundary: str) -> bytes:
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode()


class CursorRegister:
    def __init__(self, proxy: str = None, log_fn: Callable = print):
        from curl_cffi import requests as curl_req

        self.log = log_fn
        self.s = curl_req.Session(impersonate="safari17_0")
        if proxy:
            self.s.proxies = build_requests_proxy_config(proxy)

    def _base_headers(self, next_action, referer, boundary=None):
        ct = (
            f"multipart/form-data; boundary={boundary}"
            if boundary
            else "application/x-www-form-urlencoded"
        )
        return {
            "user-agent": UA,
            "accept": "text/x-component",
            "content-type": ct,
            "origin": AUTH,
            "referer": referer,
            "next-action": next_action,
            "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(main)%22%2C%7B%22children%22%3A%5B%22(root)%22%2C%7B%22children%22%3A%5B%22(sign-in)%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%5D%7D%5D",
        }

    def step1_get_session(self):
        nonce = str(uuid.uuid4())
        state = {"returnTo": "https://cursor.com/dashboard", "nonce": nonce}
        state_encoded = urllib.parse.quote(urllib.parse.quote(json.dumps(state)))
        url = f"{AUTH}/?state={state_encoded}"
        self.s.get(
            url, headers={"user-agent": UA, "accept": "text/html"}, allow_redirects=True
        )
        state_cookie_name = None
        for cookie in self.s.cookies.jar:
            if "state-" in cookie.name:
                state_cookie_name = cookie.name
                break
        return state_encoded, state_cookie_name

    def step2_submit_email(self, email, state_encoded):
        bd = _boundary()
        referer = f"{AUTH}/sign-up?state={state_encoded}"
        body = _multipart({"1_state": state_encoded, "email": email}, bd)
        self.s.post(
            f"{AUTH}/sign-up",
            headers=self._base_headers(ACTION_SUBMIT_EMAIL, referer, boundary=bd),
            data=body,
            allow_redirects=False,
        )

    def step3_submit_password(self, password, email, state_encoded, yescaptcha_key=""):
        captcha_token = ""
        if yescaptcha_key:
            from core.base_captcha import YesCaptcha

            self.log("获取 Turnstile token...")
            captcha_token = YesCaptcha(yescaptcha_key).solve_turnstile(
                AUTH, TURNSTILE_SITEKEY
            )
        bd = _boundary()
        referer = f"{AUTH}/sign-up?state={state_encoded}"
        body = _multipart(
            {
                "1_state": state_encoded,
                "email": email,
                "password": password,
                "captchaToken": captcha_token,
            },
            bd,
        )
        self.s.post(
            f"{AUTH}/sign-up",
            headers=self._base_headers(ACTION_SUBMIT_PASSWORD, referer, boundary=bd),
            data=body,
            allow_redirects=False,
        )

    def step4_submit_otp(self, otp, email, state_encoded):
        bd = _boundary()
        referer = f"{AUTH}/sign-up?state={state_encoded}"
        body = _multipart({"1_state": state_encoded, "email": email, "otp": otp}, bd)
        r = self.s.post(
            f"{AUTH}/sign-up",
            headers=self._base_headers(ACTION_MAGIC_CODE, referer, boundary=bd),
            data=body,
            allow_redirects=False,
        )
        loc = r.headers.get("location", "")
        m = re.search(r"code=([\w-]+)", loc)
        return m.group(1) if m else ""

    def step5_get_token(self, auth_code, state_encoded):
        url = f"{CURSOR}/api/auth/callback?code={auth_code}&state={state_encoded}"
        self.s.get(
            url,
            headers={"user-agent": UA, "accept": "text/html"},
            allow_redirects=False,
        )
        for cookie in self.s.cookies.jar:
            if cookie.name == "WorkosCursorSessionToken":
                return urllib.parse.unquote(cookie.value)
        self.s.get(url, headers={"user-agent": UA}, allow_redirects=True)
        for cookie in self.s.cookies.jar:
            if cookie.name == "WorkosCursorSessionToken":
                return urllib.parse.unquote(cookie.value)
        return ""

    def register(
        self,
        email: str,
        password: str = None,
        otp_callback: Optional[Callable] = None,
        yescaptcha_key: str = "",
    ) -> dict:
        if not password:
            password = _rand_password()
        self.log(f"邮箱: {email}")
        self.log("Step1: 获取 session...")
        state_encoded, _ = self.step1_get_session()
        self.log("Step2: 提交邮箱...")
        self.step2_submit_email(email, state_encoded)
        self.log("Step3: 提交密码 + Turnstile...")
        self.step3_submit_password(password, email, state_encoded, yescaptcha_key)
        self.log("等待 OTP 邮件...")
        otp = otp_callback() if otp_callback else input("OTP: ")
        if not otp:
            raise RuntimeError("未获取到验证码")
        self.log(f"验证码: {otp}")
        self.log("Step4: 提交 OTP...")
        auth_code = self.step4_submit_otp(otp, email, state_encoded)
        self.log("Step5: 获取 Token...")
        token = self.step5_get_token(auth_code, state_encoded)
        return {"email": email, "password": password, "token": token}
