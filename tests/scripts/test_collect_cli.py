from __future__ import annotations

import subprocess
import sys


def test_collect_script_can_be_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/collect.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Collect official trend signals" in result.stdout
