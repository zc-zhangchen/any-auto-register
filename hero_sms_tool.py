"""HeroSMS (hero-sms.com) 接码平台 API 工具。

兼容 SMS-Activate 协议，提供：
1. 获取余额
2. 购买号码（getNumberV2）
3. 轮询验证码（getStatus）
4. 设置激活状态（setStatus：完成/取消/重发）

配置项：
  - hero_sms_api_key: API 密钥（必填）
  - hero_sms_service: 服务代码（默认 "dr"，即 OpenAI）
  - hero_sms_country: 国家代码（默认 0，即任意国家）
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

HERO_SMS_BASE_URL = "https://hero-sms.com/stubs/handler_api.php"

# setStatus 状态码
STATUS_READY = 1        # 准备接收短信
STATUS_RESEND = 3       # 请求重发
STATUS_COMPLETE = 6     # 完成激活
STATUS_CANCEL = 8       # 取消激活


@dataclass(frozen=True)
class HeroSmsActivation:
    """一次 HeroSMS 激活记录。"""
    activation_id: int
    phone: str           # 含国际区号，如 "+48573583699"
    service: str
    country: int
    cost: float = 0.0


class HeroSmsError(RuntimeError):
    pass


class HeroSmsNoNumberError(HeroSmsError):
    pass


class HeroSmsAuthError(HeroSmsError):
    pass


def _build_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        },
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
    )


def _api_call(
    client: httpx.Client,
    api_key: str,
    action: str,
    params: Optional[dict] = None,
) -> str:
    """发起 HeroSMS API 请求，返回原始文本响应。"""
    query = {"api_key": api_key, "action": action}
    if params:
        query.update(params)

    resp = client.get(HERO_SMS_BASE_URL, params=query)
    resp.raise_for_status()
    text = resp.text.strip()

    # 通用错误检测
    if text.startswith("BAD_KEY") or text.startswith("NO_KEY"):
        raise HeroSmsAuthError(f"HeroSMS 认证失败: {text}")
    if text.startswith("ERROR_SQL"):
        raise HeroSmsError(f"HeroSMS 服务端错误: {text}")
    if text.startswith("BANNED"):
        raise HeroSmsError(f"HeroSMS 账号被封: {text}")

    return text


def get_balance(api_key: str) -> float:
    """获取账户余额。"""
    client = _build_client()
    try:
        text = _api_call(client, api_key, "getBalance")
        # 响应格式: "ACCESS_BALANCE:123.45"
        if ":" in text:
            return float(text.split(":")[1])
        return float(text)
    finally:
        client.close()


def get_number(
    api_key: str,
    service: str = "dr",
    country: int = 0,
    max_price: Optional[float] = None,
    operator: Optional[str] = None,
) -> HeroSmsActivation:
    """购买一个虚拟号码。

    Args:
        api_key: API 密钥
        service: 服务代码（如 "dr" 对应 OpenAI）
        country: 国家代码（0=任意）
        max_price: 最高价格限制
        operator: 运营商偏好

    Returns:
        HeroSmsActivation 对象
    """
    client = _build_client()
    try:
        params = {"service": service, "country": str(country)}
        if max_price is not None:
            params["maxPrice"] = str(max_price)
        if operator:
            params["operator"] = operator

        text = _api_call(client, api_key, "getNumberV2", params)

        # 可能返回 JSON 或旧格式 "ACCESS_NUMBER:id:phone"
        if text.startswith("ACCESS_NUMBER:"):
            parts = text.split(":")
            return HeroSmsActivation(
                activation_id=int(parts[1]),
                phone="+" + parts[2],
                service=service,
                country=country,
            )

        # 尝试 JSON 解析（V2 格式）
        import json
        try:
            data = json.loads(text)
            phone = str(data.get("phoneNumber", ""))
            if not phone.startswith("+"):
                phone = "+" + phone
            return HeroSmsActivation(
                activation_id=int(data["activationId"]),
                phone=phone,
                service=service,
                country=country,
                cost=float(data.get("activationCost", 0)),
            )
        except (json.JSONDecodeError, KeyError):
            pass

        # 错误处理
        if "NO_NUMBERS" in text:
            raise HeroSmsNoNumberError(f"HeroSMS 无可用号码: service={service}, country={country}")
        if "NO_BALANCE" in text:
            raise HeroSmsError("HeroSMS 余额不足")
        if "WRONG_SERVICE" in text:
            raise HeroSmsError(f"HeroSMS 无效服务代码: {service}")

        raise HeroSmsError(f"HeroSMS getNumber 未知响应: {text}")
    finally:
        client.close()


def set_status(api_key: str, activation_id: int, status: int) -> str:
    """设置激活状态。"""
    client = _build_client()
    try:
        return _api_call(client, api_key, "setStatus", {
            "id": str(activation_id),
            "status": str(status),
        })
    finally:
        client.close()


def get_status(api_key: str, activation_id: int) -> tuple[str, Optional[str]]:
    """查询激活状态和验证码。

    Returns:
        (status_text, code_or_none)
        status_text 可能是:
          - "STATUS_WAIT_CODE" - 等待短信
          - "STATUS_WAIT_RETRY" - 等待重发后的短信
          - "STATUS_CANCEL" - 已取消
          - "STATUS_OK:123456" - 收到验证码
    """
    client = _build_client()
    try:
        text = _api_call(client, api_key, "getStatus", {"id": str(activation_id)})

        if text.startswith("STATUS_OK:"):
            code = text.split(":", 1)[1].strip()
            return ("STATUS_OK", code)

        return (text, None)
    finally:
        client.close()


def wait_for_code(
    api_key: str,
    activation_id: int,
    *,
    timeout: float = 120.0,
    poll_interval: float = 5.0,
    trace: Optional[Callable[[str], None]] = None,
    request_resend: bool = False,
) -> Optional[str]:
    """轮询等待验证码。

    Args:
        api_key: API 密钥
        activation_id: 激活 ID
        timeout: 最大等待秒数
        poll_interval: 轮询间隔秒数
        trace: 日志回调
        request_resend: 是否请求新验证码（用于复用号码时重试）

    Returns:
        验证码字符串，超时返回 None
    """
    emit = trace or (lambda _: None)
    deadline = time.monotonic() + timeout
    poll_count = 0

    # 复用号码时先请求重发（setStatus=3），避免拿到缓存的旧验证码
    if request_resend:
        try:
            set_status(api_key, activation_id, STATUS_RESEND)
            emit(f"复用号码，请求重发新验证码 activation {activation_id}")
        except Exception as e:
            emit(f"请求重发失败（可忽略）: {e}")
    else:
        try:
            set_status(api_key, activation_id, STATUS_READY)
            emit(f"已标记 activation {activation_id} 为准备接收状态")
        except Exception as e:
            emit(f"标记准备状态失败（可忽略）: {e}")

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            emit(f"等待超时，共轮询 {poll_count} 次")
            return None

        sleep_s = min(poll_interval, max(remaining, 0))
        if sleep_s > 0:
            time.sleep(sleep_s)

        poll_count += 1
        try:
            status_text, code = get_status(api_key, activation_id)
        except Exception as e:
            emit(f"轮询 {poll_count} 失败: {e}")
            continue

        if code:
            emit(f"收到验证码: {code}（轮询 {poll_count} 次）")
            return code

        if status_text == "STATUS_CANCEL":
            emit("激活已被取消")
            return None

        if poll_count <= 3 or poll_count % 5 == 0:
            emit(f"轮询 {poll_count}: {status_text}")


def complete_activation(api_key: str, activation_id: int) -> None:
    """完成激活。"""
    try:
        set_status(api_key, activation_id, STATUS_COMPLETE)
    except Exception:
        pass


def cancel_activation(api_key: str, activation_id: int) -> None:
    """取消激活。"""
    try:
        set_status(api_key, activation_id, STATUS_CANCEL)
    except Exception:
        pass
