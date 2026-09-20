from __future__ import annotations

import pytest

from app.meta.disabled import (
    InstagramBusinessDiscoveryProvider,
    InstagramHashtagValidator,
    ThreadsKeywordProvider,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider",
    [
        InstagramHashtagValidator(),
        InstagramBusinessDiscoveryProvider(),
        ThreadsKeywordProvider(),
    ],
)
async def test_optional_meta_providers_are_disabled_without_network(provider) -> None:
    result = await provider.validate({"candidate_id": 1})

    assert result.status == "DISABLED"
    assert result.evidence == []
