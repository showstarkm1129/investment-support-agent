from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_static


class StaticValidationTests(unittest.TestCase):
    def test_static_validation_without_generated_diff(self) -> None:
        self.assertEqual(0, validate_static.run_all_checks(check_generated=False))


if __name__ == "__main__":
    unittest.main()
