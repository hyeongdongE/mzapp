from pathlib import Path


def test_activity_timer_is_foreground_bounded_and_flushes_lifecycle_events() -> None:
    source = Path("dashboard/static/brief_quality.js").read_text(encoding="utf-8")

    assert 'document.visibilityState === "visible"' in source
    assert "document.hasFocus()" in source
    assert "Math.min(30, activeSeconds)" in source
    assert "setInterval(sample, 1000)" in source
    assert "setInterval(flush, 15000)" in source
    assert '"blur", "pagehide"' in source
    assert 'document.addEventListener("visibilitychange"' in source
    assert 'document.addEventListener("submit", flush)' in source
    assert "crypto.randomUUID()" in source
    assert "pendingPulse" in source
    assert "sessionStorage.setItem" in source
    assert "sessionStorage.removeItem" in source
    assert "response.ok" in source
    assert "pendingPulse = null" in source
