"""CI-gate the public completeness proof so it can never silently regress.

Loads examples/verify_golden.py and asserts the proof passes (exit 0). This is
the reproducible artifact a prospect/DPO runs before trusting the tool; if any
planted PHI channel ever survives, this test fails the build.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def test_golden_completeness_proof_passes() -> None:
    proof_path = Path(__file__).resolve().parent.parent / "examples" / "verify_golden.py"
    spec = importlib.util.spec_from_file_location("verify_golden", proof_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.run_proof() == 0
