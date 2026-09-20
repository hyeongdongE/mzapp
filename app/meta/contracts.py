from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    status: Literal["DISABLED", "VALIDATED"]
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class MetaValidationProvider(Protocol):
    async def validate(self, candidate: dict[str, Any]) -> ValidationResult: ...
