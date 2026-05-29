"""Public completeness proof — run it yourself:

    python examples/verify_golden.py

Builds a synthetic study with PHI planted in EVERY channel dcm-anon must handle
(standard tags, vendor private blocks, nested-sequence PHI, identifiers the
legacy table missed, an SR free-text content tree), anonymises it, and asserts
the output is clean across independent checks. Exit 0 = PASS, nonzero = a leak.

This is the artifact a hospital DPO or research partner can reproduce on their
own machine before trusting the tool — no real patient data involved.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from pydicom import dcmread
from pydicom.dataset import Dataset

from dcm_anon import __version__, anonymize_path, scan_outputs
from dcm_anon.testkit import build_adversarial_study


def _all_elements(ds: Dataset) -> list:
    elements = []
    for elem in ds:
        elements.append(elem)
        if elem.VR == "SQ" and elem.value:
            for item in elem.value:
                elements.extend(_all_elements(item))
    return elements


def run_proof() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src_dir = root / "in"
        build_adversarial_study(src_dir)
        dst_dir = root / "out"

        anonymize_path(src_dir, dst_dir, salt="GOLDEN-PROOF-SECRET", scrub_sr=True)
        result = scan_outputs(dst_dir)

        out_files = sorted(dst_dir.rglob("*.dcm"))
        out = dcmread(out_files[0])
        all_text = " ".join(str(e.value) for e in _all_elements(out))
        private_left = [
            f"{e.tag.group:04X},{e.tag.element:04X}"
            for e in _all_elements(out)
            if e.tag.is_private
        ]
        codes = {i.CodeValue for i in getattr(out, "DeidentificationMethodCodeSequence", [])}

        checks: list[tuple[str, bool]] = [
            ("independent metadata scan reports clean", result.passed),
            ("no private/vendor tags survive (incl. nested)", private_left == []),
            ("planted SSN gone from output", "123-45-6789" not in all_text),
            ("planted email gone from output", "john@example.com" not in all_text),
            ("original MRN gone from output", "MRN-12345" not in all_text),
            ("PatientName pseudonymised", str(out.PatientName).startswith("ANON")),
            ("PatientIdentityRemoved=YES written", out.get("PatientIdentityRemoved") == "YES"),
            ("Clean Structured Content (113104) stamped", "113104" in codes),
        ]

    print(f"dcm-anon {__version__} - completeness proof on a synthetic PHI study\n")
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print()
    if ok:
        print("RESULT: PASS - every planted PHI channel was cleared.")
        return 0
    print("RESULT: FAIL - a planted PHI channel survived (see [FAIL] above).")
    return 1


if __name__ == "__main__":
    raise SystemExit(run_proof())
