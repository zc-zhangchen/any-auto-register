from .base import BaseMailImportStrategy
from .providers import AppleMailImportStrategy, MicrosoftMailImportStrategy
from .schemas import MailImportProviderDescriptor


class MailImportRegistry:
    def __init__(self, strategies: list[BaseMailImportStrategy]):
        self._strategies = {strategy.descriptor.type: strategy for strategy in strategies}
        if "microsoft" in self._strategies:
            self._strategies["outlook"] = self._strategies["microsoft"]

    def get(self, provider_type: str) -> BaseMailImportStrategy:
        strategy = self._strategies.get(str(provider_type or "").strip())
        if not strategy:
            raise ValueError(f"不支持的邮箱导入类型: {provider_type}")
        return strategy

    def descriptors(self) -> list[MailImportProviderDescriptor]:
        seen: set[str] = set()
        items: list[MailImportProviderDescriptor] = []
        for strategy in self._strategies.values():
            descriptor = strategy.descriptor
            if descriptor.type in seen:
                continue
            seen.add(descriptor.type)
            items.append(descriptor)
        return items


mail_import_registry = MailImportRegistry(
    strategies=[
        AppleMailImportStrategy(),
        MicrosoftMailImportStrategy(),
    ]
)
