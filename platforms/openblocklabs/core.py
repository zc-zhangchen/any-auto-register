"""
OpenBlockLabs 自动注册 (WorkOS AuthKit)

流程:
  1. GET auth-relay/.../initiate_signup → authorization_session_id
  2. GET auth.openblocklabs.com/sign-up?... → 提取 next-action ID
  3. POST /sign-up (first_name/last_name/email/intent=sign-up) → __Host-state cookie
  4. GET /sign-up/password → 提取 next-action ID
  5. POST /sign-up/password (password/signals/...) → pendingAuthenticationToken from RSC body
  6. GET /email-verification → 提取 next-action ID
  7. POST /email-verification (code + pending_authentication_token) → 303 → callback
  8. GET dashboard.openblocklabs.com/auth/callback?code=... → wos-session cookie
  9. GET /api/create-personal-org → 完成

pip install curl_cffi requests
"""

import re, json, time, base64, random, string, os
from urllib.parse import urlencode, urlparse, parse_qs
from curl_cffi import requests as curl_requests
import requests as std_requests
from core.proxy_utils import build_requests_proxy_config

# ─── 配置 ───────────────────────────────────────────────────────────────────

AUTH_BASE = "https://auth.openblocklabs.com"
DASHBOARD_BASE = "https://dashboard.openblocklabs.com"
DASHBOARD_CALLBACK = f"{DASHBOARD_BASE}/auth/callback"
CLIENT_ID = "client_01K8YDZSSKDMK8GYTEHBAW4N4S"
# ────────────────────────────────────────────────────────────────────────────

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


def _rand_password(n=14):
    chars = string.ascii_letters + string.digits + "!@#"
    pw = (
        random.choice(string.ascii_uppercase)
        + random.choice(string.ascii_lowercase)
        + random.choice(string.digits)
        + random.choice("!@#")
        + "".join(random.choices(chars, k=n - 4))
    )
    lst = list(pw)
    random.shuffle(lst)
    return "".join(lst)


def _build_multipart(
    fields: list, boundary: str = "----WebKitFormBoundaryPyAPI"
) -> tuple:
    body = ""
    for name, value in fields:
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
    body += f"--{boundary}--\r\n"
    return body.encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def _make_signals() -> str:
    """生成伪造的 browser signals (base64 JSON)"""
    data = {
        "createdAtMs": int(time.time() * 1000),
        "timezone": "Asia/Shanghai",
        "language": "zh-CN",
        "hardwareConcurrency": 8,
        "webdriver": False,
        "userAgent": UA,
        "appVersion": UA.split("Mozilla/5.0 ")[1] if "Mozilla" in UA else UA,
        "platform": "MacIntel",
        "screen": {
            "width": 1470,
            "height": 956,
            "availWidth": 1470,
            "availHeight": 956,
            "windowOuterWidth": 1470,
            "windowOuterHeight": 956,
            "colorDepth": 24,
            "pixelDepth": 24,
        },
        "maxTouchPoints": 0,
        "deviceMemory": 8,
        "devicePixelRatio": 2,
        "pluginsLength": 5,
        "mimeTypesCount": 2,
        "webdriver": False,
        "playwrightDetected": False,
        "phantomDetected": False,
        "nightmareDetected": False,
        "seleniumDetected": False,
        "puppeteerDetected": False,
        "submittedAtMs": int(time.time() * 1000) + 5000,
    }
    return base64.b64encode(json.dumps(data).encode()).decode()


# ─── Register ────────────────────────────────────────────────────────────────
class OpenBlockLabsRegister:
    def __init__(self, proxy: str = None):
        self.s = curl_requests.Session()
        self.s.impersonate = "chrome131"
        if proxy:
            self.s.proxies = build_requests_proxy_config(proxy)
        self.s.headers.update(
            {
                "user-agent": UA,
                "accept-language": "zh-CN,zh;q=0.9",
            }
        )
        self.authorization_session_id = None
        self._action_id = None

    def log(self, msg):
        print(f"[REG] {msg}")

    def _get_headers(self, referer: str = None, accept: str = None) -> dict:
        h = {
            "accept": accept
            or "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        if referer:
            h["referer"] = referer
        return h

    def _extract_action_id(self, text: str) -> str:
        m = re.search(r'\\?"id\\?":\\?"([a-f0-9]{40})\\?"', text)
        return m.group(1) if m else None

    def _post_action(self, url: str, fields: list, router_state: str):
        all_fields = fields + [("0", '["$K1"]')]
        body, ct = _build_multipart(all_fields)
        return self.s.post(
            url,
            data=body,
            headers={
                "accept": "text/x-component",
                "content-type": ct,
                "origin": AUTH_BASE,
                "referer": url,
                "next-action": self._action_id,
                "next-router-state-tree": router_state,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
            allow_redirects=False,
        )

    def step1_initiate_signup(self) -> bool:
        """GET auth.openblocklabs.com/sign-up → authorization_session_id + action ID"""
        self.log("Step1: GET /sign-up")
        for attempt in range(5):
            r = self.s.get(
                f"{AUTH_BASE}/sign-up",
                params={"redirect_uri": DASHBOARD_CALLBACK},
                headers=self._get_headers(),
                allow_redirects=True,
            )
            if r.status_code == 200:
                break
            self.log(f"  CF拦截 (status={r.status_code}), 重试 {attempt + 1}/5...")
            time.sleep(2)
        final_url = str(r.url)
        parsed = urlparse(final_url)
        qs = parse_qs(parsed.query)
        self.authorization_session_id = qs.get("authorization_session_id", [None])[0]
        if not self.authorization_session_id:
            for rr in r.history:
                loc = rr.headers.get("location", "")
                m = re.search(r"authorization_session_id=([^&]+)", loc)
                if m:
                    self.authorization_session_id = m.group(1)
                    break
        self._action_id = self._extract_action_id(r.text)
        self.log(
            f"  session_id={self.authorization_session_id}, action={self._action_id and self._action_id[:16]}..."
        )
        return bool(self.authorization_session_id)

    def step2_get_signup_page(self) -> bool:
        """已在 step1 完成，直接返回 True"""
        return bool(self.authorization_session_id)

    def step3_submit_signup(self, email: str, first_name: str, last_name: str) -> bool:
        """POST /sign-up (first_name/last_name/email/intent=sign-up) → 303 → /sign-up/password"""
        self.log(f"Step3: POST /sign-up email={email}")
        url = f"{AUTH_BASE}/sign-up?" + urlencode(
            {
                "redirect_uri": DASHBOARD_CALLBACK,
                "authorization_session_id": self.authorization_session_id,
            }
        )
        router_state = (
            "%5B%22%22%2C%7B%22children%22%3A%5B%22%28main%29%22%2C%7B%22children%22%3A%5B%22%28root%29%22%2C"
            "%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D"
            "%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
        )
        resp = self._post_action(
            url,
            [
                ("1_browser_supports_passkeys", "true"),
                ("1_signals", ""),
                ("1_first_name", first_name),
                ("1_last_name", last_name),
                ("1_email", email),
                ("1_intent", "sign-up"),
                ("1_redirect_uri", DASHBOARD_CALLBACK),
                ("1_authorization_session_id", self.authorization_session_id),
            ],
            router_state,
        )
        self.log(f"  -> {resp.status_code}")
        return resp.status_code == 303

    def step4_get_password_page(self) -> bool:
        """GET /sign-up/password → 提取 next-action ID"""
        self.log("Step4: GET /sign-up/password")
        url = f"{AUTH_BASE}/sign-up/password?" + urlencode(
            {
                "redirect_uri": DASHBOARD_CALLBACK,
                "authorization_session_id": self.authorization_session_id,
            }
        )
        r = self.s.get(
            url,
            headers=self._get_headers(referer=f"{AUTH_BASE}/sign-up"),
            allow_redirects=True,
        )
        self.log(f"  -> {r.status_code}")
        action = self._extract_action_id(r.text)
        if action:
            self._action_id = action
            self.log(f"  action={action[:16]}...")
        return r.status_code == 200

    def step5_submit_password(
        self, email: str, password: str, first_name: str, last_name: str
    ) -> str:
        """POST /sign-up/password → RSC body 包含 pendingAuthenticationToken"""
        self.log("Step5: POST /sign-up/password")
        url = f"{AUTH_BASE}/sign-up/password?" + urlencode(
            {
                "redirect_uri": DASHBOARD_CALLBACK,
                "authorization_session_id": self.authorization_session_id,
            }
        )
        router_state = (
            "%5B%22%22%2C%7B%22children%22%3A%5B%22%28main%29%22%2C%7B%22children%22%3A%5B%22%28root%29%22%2C"
            "%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22password%22%2C%7B%22children%22%3A"
            "%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D"
            "%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
        )
        resp = self._post_action(
            url,
            [
                ("1_browser_supports_passkeys", "true"),
                ("1_signals", _make_signals()),
                ("1_first_name", first_name),
                ("1_last_name", last_name),
                ("1_email", email),
                ("1_password", password),
                ("1_intent", "sign-up"),
                ("1_redirect_uri", DASHBOARD_CALLBACK),
                ("1_authorization_session_id", self.authorization_session_id),
            ],
            router_state,
        )
        self.log(f"  -> {resp.status_code}")
        body = resp.text
        m = re.search(r'"pendingAuthenticationToken"\s*:\s*"([^"]+)"', body)
        token = m.group(1) if m else None
        self.log(f"  pendingAuthenticationToken={token}")
        if not token:
            self.log(f"  body[:600]: {body[:600]}")
        return token

    def step6_get_email_verification_page(self) -> bool:
        """GET /email-verification → 提取 next-action ID"""
        self.log("Step6: GET /email-verification")
        url = f"{AUTH_BASE}/email-verification?" + urlencode(
            {
                "redirect_uri": DASHBOARD_CALLBACK,
                "authorization_session_id": self.authorization_session_id,
            }
        )
        r = self.s.get(
            url,
            headers=self._get_headers(referer=f"{AUTH_BASE}/sign-up/password"),
            allow_redirects=True,
        )
        self.log(f"  -> {r.status_code}")
        action = self._extract_action_id(r.text)
        if action:
            self._action_id = action
            self.log(f"  action={action[:16]}...")
        return r.status_code == 200

    def step7_submit_otp(self, email: str, code: str, pending_auth_token: str) -> str:
        """POST /email-verification → 303 → dashboard/auth/callback?code=..."""
        self.log(f"Step7: POST /email-verification code={code}")
        url = f"{AUTH_BASE}/email-verification?" + urlencode(
            {
                "redirect_uri": DASHBOARD_CALLBACK,
                "authorization_session_id": self.authorization_session_id,
            }
        )
        fields = [
            ("1_code", code),
            ("1_redirect_uri", DASHBOARD_CALLBACK),
            ("1_authorization_session_id", self.authorization_session_id),
            ("1_email", email),
        ]
        if pending_auth_token:
            fields.append(("1_pending_authentication_token", pending_auth_token))
        fields.append(("0", '["$K1"]'))
        body, ct = _build_multipart(fields)
        resp = self.s.post(
            url,
            data=body,
            headers={
                "accept": "text/x-component",
                "content-type": ct,
                "origin": AUTH_BASE,
                "referer": url,
                "next-action": self._action_id,
                "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22%28main%29%22%2C%7B%22children%22%3A%5B%22%28root%29%22%2C%7B%22children%22%3A%5B%22%28fixed-layout%29%22%2C%7B%22children%22%3A%5B%22email-verification%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
            allow_redirects=False,
        )
        self.log(f"  -> {resp.status_code}")
        redirect = resp.headers.get("x-action-redirect", "")
        self.log(f"  x-action-redirect: {redirect[:120]}")
        if not redirect:
            self.log(f"  body[:400]: {resp.text[:400]}")
        m = re.search(r"code=([^&]+)", redirect)
        auth_code = m.group(1) if m else None
        self.log(f"  auth_code={auth_code}")
        return auth_code

    def step8_exchange_callback(self, auth_code: str) -> str:
        """GET dashboard/auth/callback?code=... → wos-session cookie"""
        self.log("Step8: GET /auth/callback")
        url = f"{DASHBOARD_CALLBACK}?code={auth_code}"
        r = self.s.get(
            url, headers=self._get_headers(referer=AUTH_BASE), allow_redirects=True
        )
        self.log(f"  -> {r.status_code} final={str(r.url)[:80]}")
        for c in self.s.cookies.jar:
            if "wos-session" in c.name:
                return c.value
        return None

    def step9_create_personal_org(self) -> bool:
        """GET /api/create-personal-org → 完成组织创建"""
        self.log("Step9: GET /api/create-personal-org")
        r = self.s.get(
            f"{DASHBOARD_BASE}/api/create-personal-org",
            headers=self._get_headers(referer=f"{DASHBOARD_BASE}/"),
            allow_redirects=True,
        )
        self.log(f"  -> {r.status_code} final={str(r.url)[:80]}")
        return r.status_code == 200

    def register(
        self,
        email: str = None,
        password: str = None,
        first_name: str = None,
        last_name: str = None,
        account_id: str = None,
        otp_callback=None,
    ) -> dict:
        if not password:
            password = _rand_password()
        if not first_name:
            first_name = "".join(
                random.choices(string.ascii_lowercase, k=5)
            ).capitalize()
        if not last_name:
            last_name = random.choice(string.ascii_uppercase)

        if not self.step1_initiate_signup():
            return {"success": False, "error": "initiate_signup failed"}
        if not self.step2_get_signup_page():
            return {"success": False, "error": "get_signup_page failed"}
        if not self.step3_submit_signup(email, first_name, last_name):
            return {"success": False, "error": "submit_signup failed"}
        if not self.step4_get_password_page():
            return {"success": False, "error": "get_password_page failed"}

        pending_token = self.step5_submit_password(
            email, password, first_name, last_name
        )
        if pending_token is None:
            return {
                "success": False,
                "error": "submit_password failed (email may already be registered)",
            }

        if not self.step6_get_email_verification_page():
            return {"success": False, "error": "get_email_verification_page failed"}

        if not otp_callback:
            raise RuntimeError("otp_callback is required")
        otp = otp_callback()
        if not otp:
            return {"success": False, "error": "OTP timeout"}

        auth_code = self.step7_submit_otp(email, otp, pending_token)
        if not auth_code:
            return {"success": False, "error": "submit_otp failed / no auth_code"}

        session_token = self.step8_exchange_callback(auth_code)
        if not session_token:
            return {
                "success": False,
                "error": "exchange_callback failed / no wos-session",
            }

        self.step9_create_personal_org()

        result = {
            "success": True,
            "email": email,
            "password": password,
            "wos_session": session_token,
        }
        self.log(f"注册成功: {email}")
        return result
