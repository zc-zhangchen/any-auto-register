from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

from smstome_tool import (
    PhoneEntry,
    get_unused_phone,
    mark_phone_blacklisted,
    parse_country_slugs,
    update_global_phone_list,
    wait_for_otp,
)

from hero_sms_tool import (
    HeroSmsActivation,
    HeroSmsError,
    HeroSmsNoNumberError,
    cancel_activation as hero_cancel,
    complete_activation as hero_complete,
    get_balance as hero_get_balance,
    get_number as hero_get_number,
    wait_for_code as hero_wait_for_code,
)


def _to_positive_int(value, default: int, *, minimum: int = 1) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return default
    return parsed if parsed >= minimum else default


def _prefix_hint(phone: str, width: int = 7) -> str:
    value = str(phone or "").strip()
    return value[: min(len(value), width)] if value else ""


class SMSToMePhoneService:
    def __init__(self, config: Optional[dict] = None, log_fn: Optional[Callable[[str], None]] = None):
        self.config = dict(config or {})
        self.log_fn = log_fn or (lambda _msg: None)
        self.cookie_header = str(self.config.get("smstome_cookie", "") or "").strip() or None
        self.country_slugs = parse_country_slugs(self.config.get("smstome_country_slugs"))
        self.global_file = Path(str(self.config.get("smstome_global_file") or "smstome_all_numbers.txt"))
        self.used_numbers_dir = Path(str(self.config.get("smstome_used_numbers_dir") or "smstome_used"))
        self.task_name = str(self.config.get("smstome_task_name") or "chatgpt_add_phone").strip() or "chatgpt_add_phone"
        self.max_attempts = _to_positive_int(self.config.get("smstome_phone_attempts"), 3)
        self.otp_timeout_seconds = _to_positive_int(self.config.get("smstome_otp_timeout_seconds"), 45, minimum=10)
        self.poll_interval_seconds = _to_positive_int(self.config.get("smstome_poll_interval_seconds"), 5, minimum=1)
        self.sync_max_pages_per_country = _to_positive_int(
            self.config.get("smstome_sync_max_pages_per_country"),
            5,
        )

    @property
    def enabled(self) -> bool:
        return self._has_pool_file() or bool(self.cookie_header)

    def prefix_hint(self, phone: str) -> str:
        return _prefix_hint(phone)

    def _has_pool_file(self) -> bool:
        try:
            return self.global_file.exists() and self.global_file.stat().st_size > 0
        except OSError:
            return False

    def ensure_pool_ready(self) -> None:
        if self._has_pool_file():
            return
        if not self.cookie_header:
            raise RuntimeError("未找到 SMSToMe 号码池文件，且未配置 smstome_cookie")

        self.log_fn("SMSToMe 号码池不存在，开始自动同步...")
        count = update_global_phone_list(
            cookie_header=self.cookie_header,
            countries=self.country_slugs or None,
            output_path=self.global_file,
            max_pages_per_country=self.sync_max_pages_per_country,
        )
        if count <= 0:
            raise RuntimeError("SMSToMe 号码池同步后为空")
        self.log_fn(f"SMSToMe 号码池同步完成，共 {count} 个号码")

    def acquire_phone(self, *, exclude_prefixes: Optional[Iterable[str]] = None) -> Optional[PhoneEntry]:
        self.ensure_pool_ready()
        return get_unused_phone(
            self.task_name,
            country_slug=self.country_slugs or None,
            global_file=self.global_file,
            used_numbers_dir=self.used_numbers_dir,
            exclude_prefixes=exclude_prefixes,
        )

    def mark_blacklisted(self, phone: str) -> None:
        mark_phone_blacklisted(self.task_name, phone, used_numbers_dir=self.used_numbers_dir)

    def wait_for_code(self, entry: PhoneEntry, *, timeout: Optional[int] = None) -> Optional[str]:
        wait_seconds = _to_positive_int(timeout, self.otp_timeout_seconds, minimum=10)
        return wait_for_otp(
            entry,
            cookie_header=self.cookie_header,
            timeout=wait_seconds,
            poll_interval=self.poll_interval_seconds,
            trace=lambda message: self.log_fn(f"[SMSToMe] {message}"),
            raise_on_timeout=False,
        )

    def release_phone(self) -> None:
        """SMSToMe 不需要释放号码（号码池模型）。"""
        pass


class HeroSmsPhoneService:
    """基于 HeroSMS (hero-sms.com) API 的接码服务。

    配置项：
      - hero_sms_api_key: API 密钥（必填）
      - hero_sms_service: 服务代码（默认 "dr"，OpenAI）
      - hero_sms_country: 国家代码（默认 0，任意国家）
      - hero_sms_max_price: 最高单价限制
      - hero_sms_phone_attempts: 最大尝试次数（默认 3）
      - hero_sms_otp_timeout_seconds: 验证码等待超时（默认 120 秒）
      - hero_sms_poll_interval_seconds: 轮询间隔（默认 5 秒）
    """

    # 类级别复用缓存（跨实例共享，用于跨注册任务复用同一号码）
    _shared_reusable_activation: Optional["HeroSmsActivation"] = None
    _shared_reusable_entry: Optional[PhoneEntry] = None

    def __init__(self, config: Optional[dict] = None, log_fn: Optional[Callable[[str], None]] = None):
        self.config = dict(config or {})
        self.log_fn = log_fn or (lambda _msg: None)
        self.api_key = str(self.config.get("hero_sms_api_key", "") or "").strip()
        self.service = str(self.config.get("hero_sms_service", "") or "").strip() or "dr"
        self.country = int(self.config.get("hero_sms_country", 0) or 0)
        self.max_price = None
        _mp = self.config.get("hero_sms_max_price")
        if _mp is not None and str(_mp).strip():
            try:
                self.max_price = float(str(_mp).strip())
            except ValueError:
                pass
        self.max_attempts = _to_positive_int(self.config.get("hero_sms_phone_attempts"), 3)
        self.otp_timeout_seconds = _to_positive_int(self.config.get("hero_sms_otp_timeout_seconds"), 120, minimum=10)
        self.poll_interval_seconds = _to_positive_int(self.config.get("hero_sms_poll_interval_seconds"), 5, minimum=1)
        self.reuse_number = str(self.config.get("hero_sms_reuse_number", "") or "").strip().lower() in ("1", "true", "yes", "on")
        # 当前激活记录，用于 wait_for_code / complete / cancel
        self._current_activation: Optional[HeroSmsActivation] = None
        # 复用缓存：上一次成功接码的激活记录和 PhoneEntry
        self._reusable_activation: Optional[HeroSmsActivation] = None
        self._reusable_entry: Optional[PhoneEntry] = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def prefix_hint(self, phone: str) -> str:
        return _prefix_hint(phone)

    def acquire_phone(self, *, exclude_prefixes: Optional[Iterable[str]] = None) -> Optional[PhoneEntry]:
        """购买一个虚拟号码，返回兼容 PhoneEntry 的对象。复用模式下优先返回上次的号码。"""
        if not self.api_key:
            return None

        # 复用模式：优先复用上一次成功接码的号码（类级别缓存，跨实例共享）
        if self.reuse_number and HeroSmsPhoneService._shared_reusable_activation and HeroSmsPhoneService._shared_reusable_entry:
            self._current_activation = HeroSmsPhoneService._shared_reusable_activation
            self.log_fn(
                f"[HeroSMS] 复用号码: {HeroSmsPhoneService._shared_reusable_activation.phone} "
                f"(id={HeroSmsPhoneService._shared_reusable_activation.activation_id})"
            )
            return HeroSmsPhoneService._shared_reusable_entry

        try:
            self.log_fn(f"[HeroSMS] 购买号码: service={self.service}, country={self.country}")
            activation = hero_get_number(
                api_key=self.api_key,
                service=self.service,
                country=self.country,
                max_price=self.max_price,
            )
            self._current_activation = activation
            self.log_fn(f"[HeroSMS] 获得号码: {activation.phone} (id={activation.activation_id}, cost={activation.cost})")
            entry = PhoneEntry(
                country_slug=f"hero_sms_{activation.country}",
                phone=activation.phone,
                detail_url=f"hero-sms://activation/{activation.activation_id}",
            )
            return entry
        except HeroSmsNoNumberError:
            self.log_fn("[HeroSMS] 无可用号码")
            return None
        except HeroSmsError as e:
            self.log_fn(f"[HeroSMS] 购买号码失败: {e}")
            return None

    def mark_blacklisted(self, phone: str) -> None:
        """取消当前激活（复用模式下清除复用缓存）。"""
        if self._current_activation and self._current_activation.phone == phone:
            self.log_fn(f"[HeroSMS] 取消激活: {self._current_activation.activation_id}")
            hero_cancel(self.api_key, self._current_activation.activation_id)
            # 号码被拉黑，清除类级别复用缓存
            if HeroSmsPhoneService._shared_reusable_activation and HeroSmsPhoneService._shared_reusable_activation.activation_id == self._current_activation.activation_id:
                HeroSmsPhoneService._shared_reusable_activation = None
                HeroSmsPhoneService._shared_reusable_entry = None
            self._current_activation = None

    def release_phone(self) -> None:
        """注册成功后调用：完成当前激活并清除跨账号复用缓存。

        保证下一个账号会买新号码，避免 OpenAI 检测到同一号码绑定多账号。
        注意：本次账号内部的重试仍会复用（缓存在 wait_for_code 中设置）。
        """
        if self._current_activation:
            try:
                hero_complete(self.api_key, self._current_activation.activation_id)
                self.log_fn(f"[HeroSMS] 注册成功，已完成激活: {self._current_activation.activation_id}")
            except Exception as e:
                self.log_fn(f"[HeroSMS] 完成激活失败（可忽略）: {e}")
        # 清除跨账号缓存，下个账号必须买新号码
        HeroSmsPhoneService._shared_reusable_activation = None
        HeroSmsPhoneService._shared_reusable_entry = None
        self._current_activation = None

    def wait_for_code(self, entry: PhoneEntry, *, timeout: Optional[int] = None) -> Optional[str]:
        """轮询等待验证码。"""
        if not self._current_activation:
            self.log_fn("[HeroSMS] 无当前激活记录，无法等待验证码")
            return None
        wait_seconds = _to_positive_int(timeout, self.otp_timeout_seconds, minimum=10)
        # 复用号码场景：当前激活 = 共享缓存的激活，需要请求重发新验证码
        is_reused = (
            HeroSmsPhoneService._shared_reusable_activation is not None
            and HeroSmsPhoneService._shared_reusable_activation.activation_id
            == self._current_activation.activation_id
        )
        code = hero_wait_for_code(
            api_key=self.api_key,
            activation_id=self._current_activation.activation_id,
            timeout=wait_seconds,
            poll_interval=self.poll_interval_seconds,
            trace=lambda message: self.log_fn(f"[HeroSMS] {message}"),
            request_resend=is_reused,
        )
        if code:
            if self.reuse_number:
                # 复用模式：不 complete，保持号码活跃，缓存到类级别供下次注册使用
                HeroSmsPhoneService._shared_reusable_activation = self._current_activation
                HeroSmsPhoneService._shared_reusable_entry = entry
                self.log_fn(f"[HeroSMS] 复用模式：保持激活 {self._current_activation.activation_id}，号码可继续接码")
            else:
                # 非复用模式：立即 complete
                hero_complete(self.api_key, self._current_activation.activation_id)
                self.log_fn(f"[HeroSMS] 激活完成: {self._current_activation.activation_id}")
        return code
