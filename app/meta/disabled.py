from __future__ import annotations

from typing import Any

from app.meta.contracts import ValidationResult


class DisabledMetaValidationProvider:
    async def validate(self, candidate: dict[str, Any]) -> ValidationResult:
        del candidate
        return ValidationResult(status="DISABLED", evidence=[])


class InstagramHashtagValidator(DisabledMetaValidationProvider):
    pass


class InstagramBusinessDiscoveryProvider(DisabledMetaValidationProvider):
    pass


class ThreadsKeywordProvider(DisabledMetaValidationProvider):
    pass
