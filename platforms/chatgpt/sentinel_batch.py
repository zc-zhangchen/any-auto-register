"""Standalone Sentinel SDK batch token helper."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Protocol

from core.browser_runtime import (
    ensure_browser_display_available,
    resolve_browser_headless,
)
from core.config_store import ConfigStore, config_store
from core.proxy_pool import ProxyPool, proxy_pool
from core.proxy_utils import build_playwright_proxy_config, normalize_proxy_url


DEFAULT_SDK_VERSION = "20260219f9f6"
DEFAULT_FRAME_URL = f"https://sentinel.openai.com/backend-api/sentinel/frame.html?sv={DEFAULT_SDK_VERSION}"
DEFAULT_SDK_URL = f"https://sentinel.openai.com/sentinel/{DEFAULT_SDK_VERSION}/sdk.js"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.7103.92 Safari/537.36"
)
DEFAULT_OUT = Path(tempfile.gettempdir()) / "sentinel_multi_helper_out.json"
DEFAULT_FLOW_SPECS: tuple["FlowSpec", ...]


@dataclass(frozen=True)
class FlowSpec:
    internal_name: str
    alias: str
    page_url: str
    needs_session_observer_token: bool = False


DEFAULT_FLOW_SPECS = (
    FlowSpec(
        internal_name="authorize_continue",
        alias="authorize-continue",
        page_url="https://auth.openai.com/create-account",
    ),
    FlowSpec(
        internal_name="username_password_create",
        alias="username-password-create",
        page_url="https://auth.openai.com/create-account/password",
    ),
    FlowSpec(
        internal_name="password_verify",
        alias="password-verify",
        page_url="https://auth.openai.com/log-in/password",
    ),
    FlowSpec(
        internal_name="oauth_create_account",
        alias="oauth-create-account",
        page_url="https://auth.openai.com/about-you",
        needs_session_observer_token=True,
    ),
)


@dataclass(frozen=True)
class SentinelBatchConfig:
    frame_url: str
    sdk_url: str
    user_agent: str
    output_path: Path
    proxy: Optional[str]
    flows: tuple[FlowSpec, ...]
    headless: bool = True
    headless_reason: str = ""


@dataclass
class FlowTokenResult:
    flow: str
    page_url: str
    sentinel_token: Optional[str] = None
    sentinel_so_token: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "flow": self.flow,
            "pageUrl": self.page_url,
        }
        if self.sentinel_token:
            data["sentinel-token"] = self.sentinel_token
        if self.sentinel_so_token:
            data["sentinel-so-token"] = self.sentinel_so_token
        if self.error:
            data["error"] = self.error
        return data


@dataclass
class SentinelBatchResult:
    generated_at: str
    device_id: str
    proxy: Optional[str]
    frame_url: str
    sdk_url: str
    user_agent: str
    flows: dict[str, FlowTokenResult] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(item.error for item in self.flows.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "generatedAt": self.generated_at,
            "deviceId": self.device_id,
            "proxy": self.proxy or "",
            "frameUrl": self.frame_url,
            "sdkUrl": self.sdk_url,
            "userAgent": self.user_agent,
            "flows": {alias: item.to_dict() for alias, item in self.flows.items()},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class ProxySelector(Protocol):
    def select_proxy(self) -> Optional[str]: ...


class SentinelProvider(ABC):
    @abstractmethod
    def __enter__(self) -> "SentinelProvider":
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type, exc, tb) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_flow_token(self, flow: FlowSpec) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_session_observer_token(self, flow: FlowSpec) -> str:
        raise NotImplementedError

    @abstractmethod
    def resolved_sdk_url(self) -> str:
        raise NotImplementedError


class ConfigBackedProxySelector:
    """Resolve proxy from explicit config/env values and then proxy pool."""

    EXPLICIT_PROXY_KEYS = (
        "PROXY_SERVER",
        "proxy_server",
        "sentinel_proxy_server",
        "sentinel.proxy_server",
        "proxy_url",
        "proxy.url",
    )

    def __init__(
        self,
        config: ConfigStore = config_store,
        pool: ProxyPool = proxy_pool,
    ) -> None:
        self._config = config
        self._pool = pool

    def _get_first(self, keys: Iterable[str]) -> str:
        for key in keys:
            value = str(self._config.get(key, "") or "").strip()
            if value:
                return value
        return ""

    def _build_from_global_proxy_config(self) -> str:
        enabled = str(self._config.get("proxy.enabled", "") or "").strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return ""

        host = str(self._config.get("proxy.host", "") or "").strip()
        if not host:
            return ""

        scheme = str(self._config.get("proxy.type", "http") or "http").strip() or "http"
        port = str(self._config.get("proxy.port", "") or "").strip()
        user = str(self._config.get("proxy.username", "") or "").strip()
        password = str(self._config.get("proxy.password", "") or "").strip()

        auth = ""
        if user:
            auth = user
            if password:
                auth += f":{password}"
            auth += "@"

        if port:
            return f"{scheme}://{auth}{host}:{port}"
        return f"{scheme}://{auth}{host}"

    def select_proxy(self) -> Optional[str]:
        explicit_proxy = self._get_first(self.EXPLICIT_PROXY_KEYS)
        if explicit_proxy:
            return normalize_proxy_url(explicit_proxy)

        global_proxy = self._build_from_global_proxy_config()
        if global_proxy:
            return normalize_proxy_url(global_proxy)

        return normalize_proxy_url(self._pool.get_next() or None)


class ConfigResolver:
    """Resolve runtime config with clear precedence rules."""

    def __init__(
        self,
        config: ConfigStore = config_store,
        proxy_selector: Optional[ProxySelector] = None,
        environ: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._config = config
        self._proxy_selector = proxy_selector or ConfigBackedProxySelector(
            config=config
        )
        self._environ = environ if environ is not None else os.environ

    def _get(self, key: str, default: str = "") -> str:
        if key in self._environ:
            value = str(self._environ.get(key, "") or "").strip()
            if value:
                return value
        return str(self._config.get(key, default) or default).strip()

    def _resolve_output_path(self) -> Path:
        out_value = self._get("OUT", "")
        return Path(out_value).expanduser() if out_value else DEFAULT_OUT

    def _resolve_flows(self) -> tuple[FlowSpec, ...]:
        flow_alias_map = {spec.internal_name: spec for spec in DEFAULT_FLOW_SPECS} | {
            spec.alias: spec for spec in DEFAULT_FLOW_SPECS
        }
        flows_raw = self._get("FLOWS", "")
        if not flows_raw:
            return DEFAULT_FLOW_SPECS

        selected: list[FlowSpec] = []
        for item in flows_raw.split(","):
            key = item.strip()
            if not key:
                continue
            spec = flow_alias_map.get(key)
            if not spec:
                raise ValueError(f"Unsupported sentinel flow: {key}")
            if spec not in selected:
                selected.append(spec)
        return tuple(selected) or DEFAULT_FLOW_SPECS

    def resolve(self) -> SentinelBatchConfig:
        requested_headless = None
        if "HEADLESS" in self._environ:
            requested_headless = self._environ.get(
                "HEADLESS", ""
            ).strip().lower() not in {
                "",
                "0",
                "false",
                "no",
                "off",
            }

        headless, reason = resolve_browser_headless(requested_headless)
        proxy = self._proxy_selector.select_proxy()
        return SentinelBatchConfig(
            frame_url=self._get("FRAME_URL", DEFAULT_FRAME_URL) or DEFAULT_FRAME_URL,
            sdk_url=self._get("SDK_URL", DEFAULT_SDK_URL) or DEFAULT_SDK_URL,
            user_agent=self._get("UA", DEFAULT_USER_AGENT) or DEFAULT_USER_AGENT,
            output_path=self._resolve_output_path(),
            proxy=proxy,
            flows=self._resolve_flows(),
            headless=headless,
            headless_reason=reason,
        )


class PlaywrightSentinelProvider(SentinelProvider):
    """Fetch Sentinel tokens through the browser SDK in a single session."""

    def __init__(
        self,
        config: SentinelBatchConfig,
        *,
        device_id: str,
        timeout_ms: int = 60000,
    ) -> None:
        self._config = config
        self._device_id = device_id
        self._timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._resolved_sdk_url = config.sdk_url

    def __enter__(self) -> "PlaywrightSentinelProvider":
        from playwright.sync_api import sync_playwright

        ensure_browser_display_available(self._config.headless)
        self._playwright = sync_playwright().start()

        launch_kwargs: dict[str, object] = {
            "headless": self._config.headless,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        }
        proxy_config = build_playwright_proxy_config(self._config.proxy)
        if proxy_config:
            launch_kwargs["proxy"] = proxy_config

        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        self._context = self._browser.new_context(
            user_agent=self._config.user_agent,
            locale="en-US",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        self._context.add_cookies(
            [
                {
                    "name": "oai-did",
                    "value": self._device_id,
                    "url": "https://sentinel.openai.com/",
                    "path": "/",
                    "secure": True,
                    "sameSite": "Lax",
                },
                {
                    "name": "oai-did",
                    "value": self._device_id,
                    "url": "https://auth.openai.com/",
                    "path": "/",
                    "secure": True,
                    "sameSite": "Lax",
                },
            ]
        )
        self._page = self._context.new_page()
        self._page.goto(
            self._config.frame_url, wait_until="load", timeout=self._timeout_ms
        )
        self._ensure_sdk_loaded()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def _ensure_sdk_loaded(self) -> None:
        assert self._page is not None
        self._page.wait_for_load_state("load", timeout=self._timeout_ms)
        try:
            self._page.wait_for_function(
                "() => !!window.SentinelSDK",
                timeout=min(self._timeout_ms, 15000),
            )
        except Exception:
            self._inject_expected_sdk()
            self._page.wait_for_function(
                "() => !!window.SentinelSDK",
                timeout=min(self._timeout_ms, 30000),
            )

        self._resolved_sdk_url = self._page.evaluate(
            """
            (expectedSdkUrl) => {
                const scripts = Array.from(document.scripts || [])
                    .map((item) => item.src)
                    .filter(Boolean);
                return scripts.find((src) => src.includes('/sdk.js')) || expectedSdkUrl;
            }
            """,
            self._config.sdk_url,
        )

    def _inject_expected_sdk(self) -> None:
        assert self._page is not None
        self._page.evaluate(
            """
            async (sdkUrl) => {
                const existing = Array.from(document.scripts || [])
                    .some((item) => item.src === sdkUrl);
                if (existing) return;
                await new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = sdkUrl;
                    script.async = true;
                    script.onload = () => resolve(true);
                    script.onerror = () => reject(new Error(`Failed to load ${sdkUrl}`));
                    document.head.appendChild(script);
                });
            }
            """,
            self._config.sdk_url,
        )

    def _invoke_sdk(self, method: str, flow: FlowSpec) -> str:
        assert self._page is not None
        result = self._page.evaluate(
            """
            async ({ flow, methodName }) => {
                if (!window.SentinelSDK) {
                    throw new Error('SentinelSDK missing');
                }
                const target = window.SentinelSDK[methodName];
                if (typeof target !== 'function') {
                    throw new Error(`SentinelSDK.${methodName} missing`);
                }
                if (typeof window.SentinelSDK.init === 'function') {
                    await window.SentinelSDK.init(flow);
                }
                return await target.call(window.SentinelSDK, flow);
            }
            """,
            {"flow": flow.internal_name, "methodName": method},
        )
        token = str(result or "").strip()
        if not token:
            raise RuntimeError(f"Empty {method} result for {flow.internal_name}")
        return token

    def get_flow_token(self, flow: FlowSpec) -> str:
        return self._invoke_sdk("token", flow)

    def get_session_observer_token(self, flow: FlowSpec) -> str:
        return self._invoke_sdk("sessionObserverToken", flow)

    def resolved_sdk_url(self) -> str:
        return self._resolved_sdk_url


class SentinelProviderFactory:
    def create(
        self,
        config: SentinelBatchConfig,
        *,
        device_id: str,
    ) -> SentinelProvider:
        return PlaywrightSentinelProvider(config=config, device_id=device_id)


class SentinelBatchService:
    def __init__(
        self,
        provider_factory: Optional[SentinelProviderFactory] = None,
        *,
        device_id_factory=None,
    ) -> None:
        self._provider_factory = provider_factory or SentinelProviderFactory()
        self._device_id_factory = device_id_factory or (lambda: str(uuid.uuid4()))

    def generate(self, config: SentinelBatchConfig) -> SentinelBatchResult:
        device_id = self._device_id_factory()
        result = SentinelBatchResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            device_id=device_id,
            proxy=config.proxy,
            frame_url=config.frame_url,
            sdk_url=config.sdk_url,
            user_agent=config.user_agent,
        )
        provider = self._provider_factory.create(config, device_id=device_id)
        with provider:
            result.sdk_url = provider.resolved_sdk_url()
            for flow in config.flows:
                item = FlowTokenResult(flow=flow.internal_name, page_url=flow.page_url)
                try:
                    item.sentinel_token = provider.get_flow_token(flow)
                    if flow.needs_session_observer_token:
                        item.sentinel_so_token = provider.get_session_observer_token(
                            flow
                        )
                except Exception as exc:  # pragma: no cover - exercised via tests
                    item.error = str(exc)
                result.flows[flow.alias] = item
        return result


def write_batch_result(result: SentinelBatchResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.to_json(), encoding="utf-8")
