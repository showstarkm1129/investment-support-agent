#!/usr/bin/env python3
"""Run the Python test suite with the best available local runner."""

from __future__ import annotations

import importlib.util
import subprocess
import sys


def main() -> int:
    if importlib.util.find_spec("pytest") is not None:
        args = sys.argv[1:] or ["tests"]
        command = [sys.executable, "-m", "pytest", *args]
    else:
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
