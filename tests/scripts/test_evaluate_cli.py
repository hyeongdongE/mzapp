from __future__ import annotations

import subprocess
import sys


def test_evaluate_script_can_be_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/evaluate.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Generate deterministic trend evaluation reports" in result.stdout
