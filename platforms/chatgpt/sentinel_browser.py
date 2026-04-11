"""Playwright 版 Sentinel SDK token 获取辅助。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from core.browser_runtime import (
    ensure_browser_display_available,
    resolve_browser_headless,
)
from core.proxy_utils import (
    build_playwright_proxy_config,
    build_requests_proxy_config,
    is_authenticated_socks5_proxy,
)


SENTINEL_VERSION = "20260219f9f6"
SENTINEL_SDK_URL = f"https://sentinel.openai.com/sentinel/{SENTINEL_VERSION}/sdk.js"
SENTINEL_REQ_URL = "https://sentinel.openai.com/backend-api/sentinel/req"


def _flow_page_url(flow: str) -> str:
    flow_name = str(flow or "").strip().lower()
    mapping = {
        "authorize_continue": "https://auth.openai.com/create-account",
        "username_password_create": "https://auth.openai.com/create-account/password",
        "password_verify": "https://auth.openai.com/log-in/password",
        "email_otp_validate": "https://auth.openai.com/email-verification",
        "oauth_create_account": "https://auth.openai.com/about-you",
    }
    return mapping.get(flow_name, "https://auth.openai.com/about-you")


def _quickjs_script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "js"
        / "openai_sentinel_quickjs.js"
    )


def _resolve_node_binary() -> str:
    custom = os.getenv("OPENAI_SENTINEL_NODE_PATH", "").strip()
    return custom or "node"


def _ensure_sdk_file(session: Any, timeout_ms: int) -> Path:
    cache_dir = Path(tempfile.gettempdir()) / "openai-sentinel-demo" / SENTINEL_VERSION
    cache_dir.mkdir(parents=True, exist_ok=True)
    sdk_file = cache_dir / "sdk.js"
    if sdk_file.exists() and sdk_file.stat().st_size > 0:
        return sdk_file

    resp = session.get(
        SENTINEL_SDK_URL,
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "referer": "https://auth.openai.com/",
            "sec-fetch-dest": "script",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-site": "same-site",
        },
        timeout=max(10, int(timeout_ms / 1000)),
    )
    resp.raise_for_status()
    content = getattr(resp, "content", b"")
    if not content:
        raise RuntimeError("下载 Sentinel sdk.js 失败: 响应为空")
    sdk_file.write_bytes(content)
    return sdk_file


def _run_quickjs_action_with_node(
    *,
    action: str,
    sdk_file: Path,
    quickjs_script: Path,
    payload: dict[str, Any],
    timeout_ms: int,
) -> dict[str, Any]:
    wrapper_js = """
const fs = require('fs');
const timeoutMs = Number(process.env.OPENAI_SENTINEL_VM_TIMEOUT_MS || '10000');
const sdkFile = process.env.OPENAI_SENTINEL_SDK_FILE;
const scriptFile = process.env.OPENAI_SENTINEL_QUICKJS_SCRIPT;

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', async () => {
  try {
    const payload = JSON.parse(input || '{}');
    globalThis.__payload_json = JSON.stringify(payload);
    globalThis.__sdk_source = fs.readFileSync(sdkFile, 'utf8');
    globalThis.__vm_done = false;
    globalThis.__vm_output_json = '';
    globalThis.__vm_error = '';
    const script = fs.readFileSync(scriptFile, 'utf8');
    eval(script);

    const started = Date.now();
    while (!globalThis.__vm_done) {
      if ((Date.now() - started) > timeoutMs) {
        throw new Error('QuickJS script timeout');
      }
      await new Promise((resolve) => setTimeout(resolve, 1));
    }

    if (String(globalThis.__vm_error || '').trim()) {
      throw new Error(String(globalThis.__vm_error));
    }

    process.stdout.write(String(globalThis.__vm_output_json || ''));
  } catch (err) {
    const msg = err && err.stack ? String(err.stack) : String(err);
    process.stderr.write(msg);
    process.exit(1);
  }
});
""".strip()

    merged_payload = dict(payload)
    merged_payload["action"] = action
    process = subprocess.run(
        [_resolve_node_binary(), "-e", wrapper_js],
        input=json.dumps(merged_payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=max(10, int(timeout_ms / 1000)),
        env={
            **os.environ,
            "OPENAI_SENTINEL_SDK_FILE": str(sdk_file),
            "OPENAI_SENTINEL_QUICKJS_SCRIPT": str(quickjs_script),
            "OPENAI_SENTINEL_VM_TIMEOUT_MS": str(min(timeout_ms, 30000)),
        },
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "unknown error").strip()
        raise RuntimeError(f"QuickJS 执行失败: {detail}")
    output = (process.stdout or "").strip()
    if not output:
        raise RuntimeError("QuickJS 返回空输出")
    data = json.loads(output)
    if not isinstance(data, dict):
        raise RuntimeError("QuickJS 输出不是 JSON 对象")
    return data


def _fetch_sentinel_challenge(
    session: Any,
    *,
    device_id: str,
    flow: str,
    request_p: str,
    timeout_ms: int,
) -> dict[str, Any]:
    body = {"p": request_p, "id": device_id, "flow": flow}
    resp = session.post(
        SENTINEL_REQ_URL,
        data=json.dumps(body, separators=(",", ":")),
        headers={
            "origin": "https://sentinel.openai.com",
            "referer": f"https://sentinel.openai.com/backend-api/sentinel/frame.html?sv={SENTINEL_VERSION}",
            "content-type": "text/plain;charset=UTF-8",
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        },
        timeout=max(10, int(timeout_ms / 1000)),
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Sentinel challenge 响应不是 JSON 对象")
    return payload


def _get_sentinel_token_via_quickjs(
    *,
    flow: str,
    proxy: Optional[str],
    timeout_ms: int,
    device_id: Optional[str],
    logger: Callable[[str], None],
) -> Optional[str]:
    try:
        from curl_cffi import requests as curl_requests
    except Exception as e:
        logger(f"Sentinel QuickJS 不可用: curl_cffi 导入失败: {e}")
        return None

    quickjs_script = _quickjs_script_path()
    if not quickjs_script.exists():
        logger(f"Sentinel QuickJS 脚本不存在: {quickjs_script}")
        return None

    did = str(device_id or uuid.uuid4())
    session = curl_requests.Session(impersonate="chrome136")
    if proxy:
        session.proxies = build_requests_proxy_config(proxy)

    try:
        sdk_file = _ensure_sdk_file(session, timeout_ms)
        requirements = _run_quickjs_action_with_node(
            action="requirements",
            sdk_file=sdk_file,
            quickjs_script=quickjs_script,
            payload={"device_id": did},
            timeout_ms=timeout_ms,
        )
        request_p = str(requirements.get("request_p") or "").strip()
        if not request_p:
            logger("Sentinel QuickJS 失败: requirements 未返回 request_p")
            return None

        challenge = _fetch_sentinel_challenge(
            session,
            device_id=did,
            flow=flow,
            request_p=request_p,
            timeout_ms=timeout_ms,
        )
        c_value = str(challenge.get("token") or "").strip()
        if not c_value:
            logger("Sentinel QuickJS 失败: challenge token 为空")
            return None

        solved = _run_quickjs_action_with_node(
            action="solve",
            sdk_file=sdk_file,
            quickjs_script=quickjs_script,
            payload={
                "device_id": did,
                "request_p": request_p,
                "challenge": challenge,
            },
            timeout_ms=timeout_ms,
        )
        final_p = str(solved.get("final_p") or solved.get("p") or "").strip()
        if not final_p:
            logger("Sentinel QuickJS 失败: solve 未返回 final_p")
            return None

        t_raw = solved.get("t")
        t_value = "" if t_raw is None else str(t_raw).strip()
        if not t_value:
            logger("Sentinel QuickJS 失败: solve 未返回有效 t")
            return None

        token = json.dumps(
            {
                "p": final_p,
                "t": t_value,
                "c": c_value,
                "id": did,
                "flow": flow,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        logger("Sentinel QuickJS 成功: p=OK t=OK c=OK")
        return token
    except Exception as e:
        logger(f"Sentinel QuickJS 异常: {e}")
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass


def get_sentinel_token_via_browser(
    *,
    flow: str,
    proxy: Optional[str] = None,
    timeout_ms: int = 45000,
    page_url: Optional[str] = None,
    headless: bool = True,
    device_id: Optional[str] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """通过浏览器直接调用 SentinelSDK.token(flow) 获取完整 token。"""
    logger = log_fn or (lambda _msg: None)

    if is_authenticated_socks5_proxy(proxy):
        logger("Sentinel 检测到带认证 SOCKS5 代理: 跳过浏览器，改用 QuickJS 获取 token")
        return _get_sentinel_token_via_quickjs(
            flow=flow,
            proxy=proxy,
            timeout_ms=timeout_ms,
            device_id=device_id,
            logger=logger,
        )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger(f"Sentinel Browser 不可用: {e}")
        return None

    target_url = str(page_url or _flow_page_url(flow)).strip() or _flow_page_url(flow)
    effective_headless, reason = resolve_browser_headless(headless)
    ensure_browser_display_available(effective_headless)
    logger(
        f"Sentinel Browser 模式: {'headless' if effective_headless else 'headed'} ({reason})"
    )

    launch_args: dict[str, Any] = {
        "headless": effective_headless,
        "args": [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ],
    }
    proxy_config = build_playwright_proxy_config(proxy)
    if proxy_config:
        launch_args["proxy"] = proxy_config

    logger(f"Sentinel Browser 启动: flow={flow}, url={target_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_args)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.7103.92 Safari/537.36"
                ),
                ignore_https_errors=True,
            )
            if device_id:
                try:
                    context.add_cookies(
                        [
                            {
                                "name": "oai-did",
                                "value": str(device_id),
                                "domain": "auth.openai.com",
                                "path": "/",
                                "secure": True,
                                "sameSite": "Lax",
                            }
                        ]
                    )
                except Exception as ex:
                    logger(f"Sentinel Browser add_cookies异常: {ex}")
                    pass

            page = context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_function(
                "() => typeof window.SentinelSDK !== 'undefined' && typeof window.SentinelSDK.token === 'function'",
                timeout=min(timeout_ms, 15000),
            )

            result = page.evaluate(
                """
                async ({ flow }) => {
                    try {
                        const token = await window.SentinelSDK.token(flow);
                        return { success: true, token };
                    } catch (e) {
                        return {
                            success: false,
                            error: (e && (e.message || String(e))) || "unknown",
                        };
                    }
                }
                """,
                {"flow": flow},
            )

            if not result or not result.get("success") or not result.get("token"):
                logger(
                    "Sentinel Browser 获取失败: "
                    + str((result or {}).get("error") or "no result")
                )
                return None

            token = str(result["token"] or "").strip()
            if not token:
                logger("Sentinel Browser 返回空 token")
                return None

            try:
                parsed = json.loads(token)
                logger(
                    "Sentinel Browser 成功: "
                    f"p={'OK' if parsed.get('p') else 'X'} "
                    f"t={'OK' if parsed.get('t') else 'X'} "
                    f"c={'OK' if parsed.get('c') else 'X'}"
                )
            except Exception:
                logger(f"Sentinel Browser 成功: len={len(token)}")

            return token
        except Exception as e:
            logger(f"Sentinel Browser 异常: {e}")
            return None
        finally:
            browser.close()
