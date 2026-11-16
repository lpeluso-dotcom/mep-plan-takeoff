"""Tests for plan_index.py's command line. Run: python3 -m pytest -q"""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "plan_index.py"


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_and_exits_0(flag, tmp_path):
    """Baseline eval 2026-11-15: --help was read as a file path."""
    r = subprocess.run([sys.executable, str(SCRIPT), flag], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Usage:" in r.stdout and "plan_index.py" in r.stdout
    assert list(tmp_path.iterdir()) == []          # nothing indexed, nothing written
