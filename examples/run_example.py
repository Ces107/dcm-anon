"""Annotated example: anonymize a public test DICOM and inspect the audit log.

Run download_test_dicom.py first to fetch the test files.

This script:
1. Loads examples/data/CT_small.dcm (public pydicom test file, no real PHI).
2. Anonymizes it into examples/out/.
3. Prints a before/after comparison of selected PHI fields.
4. Shows the JSON audit log.

Usage::

    python examples/run_example.py
    python examples/run_example.py --salt my-project  # deterministic UIDs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is importable when running from the examples/ subdir.
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydicom import dcmread
from pydicom.dataset import Dataset

from dcm_anon import UIDMapper, anonymize_file

DATA_DIR = Path(__file__).parent / "data"
OUT_DIR = Path(__file__).parent / "out"

FIELDS_TO_COMPARE: list[tuple[str, str]] = [
    ("PatientName",          "0010,0010"),
    ("PatientID",            "0010,0020"),
    ("PatientBirthDate",     "0010,0030"),
    ("InstitutionName",      "0008,0080"),
    ("ReferringPhysicianName", "0008,0090"),
    ("StudyDate",            "0008,0020"),
    ("StudyInstanceUID",     "0020,000D"),
    ("SOPInstanceUID",       "0008,0018"),
]


def _get(ds: Dataset, attr: str) -> str:
    try:
        return str(getattr(ds, attr))
    except AttributeError:
        return "<absent>"


def main() -> None:
    parser = argparse.ArgumentParser(description="dcm-anon annotated example")
    parser.add_argument("--salt", default=None, help="Deterministic UID salt")
    args = parser.parse_args()

    src = DATA_DIR / "CT_small.dcm"
    if not src.exists():
        print("Test file not found. Run: python examples/download_test_dicom.py")
        sys.exit(1)

    dst = OUT_DIR / "CT_small_anon.dcm"

    # ------------------------------------------------------------------
    # Step 1: read the original and note PHI values.
    # ------------------------------------------------------------------
    original = dcmread(src)
    print("\n=== BEFORE anonymization ===")
    for attr, tag in FIELDS_TO_COMPARE:
        print(f"  ({tag}) {attr:35s}: {_get(original, attr)}")

    # ------------------------------------------------------------------
    # Step 2: anonymize.
    # ------------------------------------------------------------------
    mapper = UIDMapper(salt=args.salt)
    record = anonymize_file(src, dst, mapper)

    # ------------------------------------------------------------------
    # Step 3: read back and compare.
    # ------------------------------------------------------------------
    anonymized = dcmread(dst)
    print("\n=== AFTER anonymization ===")
    for attr, tag in FIELDS_TO_COMPARE:
        print(f"  ({tag}) {attr:35s}: {_get(anonymized, attr)}")

    # ------------------------------------------------------------------
    # Step 4: verify file-meta consistency.
    # ------------------------------------------------------------------
    print("\n=== File-meta check ===")
    media_uid = str(anonymized.file_meta.MediaStorageSOPInstanceUID)
    sop_uid = str(anonymized.SOPInstanceUID)
    match = "OK" if media_uid == sop_uid else "MISMATCH — BUG"
    print(f"  MediaStorageSOPInstanceUID == SOPInstanceUID: {match}")
    print(f"  MediaStorageSOPInstanceUID: {media_uid}")
    print(f"  SOPInstanceUID:             {sop_uid}")

    # ------------------------------------------------------------------
    # Step 5: print the audit log.
    # ------------------------------------------------------------------
    print("\n=== Audit record ===")
    print(json.dumps(record.as_dict(), indent=2))

    print(f"\nAnonymized file: {dst}")
    if args.salt:
        print(f"Salt used: {args.salt!r} — re-run with the same salt to get identical UIDs.")


if __name__ == "__main__":
    main()
