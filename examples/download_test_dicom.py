"""Generate or fetch public test DICOMs for the example runner.

We prefer pydicom's bundled `data` module when installed (no network needed);
fall back to a synthetic builder using public PS3.15 reference values when the
bundled data is unavailable. Either way, the resulting DICOMs contain NO real
patient data — placeholder synthetic metadata only.

Usage::

    python examples/download_test_dicom.py
    python examples/run_example.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
TARGET_FILES: tuple[str, ...] = ("CT_small.dcm", "MR_small.dcm")


def _try_pydicom_bundled() -> dict[str, Path]:
    """Return {name: path} when pydicom ships the bundled test files."""
    try:
        from pydicom.data import get_testdata_file
    except ImportError:
        return {}

    found: dict[str, Path] = {}
    for name in TARGET_FILES:
        try:
            p = get_testdata_file(name)
            if p:
                found[name] = Path(p)
        except Exception:
            continue
    return found


def _generate_synthetic(name: str, dst: Path) -> None:
    """Build a small synthetic DICOM with placeholder PHI; no network required."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from conftest import _make_synthetic_dcm

    burned = name.startswith("MR")
    _make_synthetic_dcm(dst, burned_in=burned)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bundled = _try_pydicom_bundled()
    for name in TARGET_FILES:
        dst = DATA_DIR / name
        if dst.exists():
            print(f"  already present: {dst}")
            continue
        if name in bundled:
            shutil.copy(bundled[name], dst)
            print(f"  copied bundled pydicom test file → {dst} ({dst.stat().st_size} bytes)")
        else:
            _generate_synthetic(name, dst)
            print(f"  generated synthetic → {dst} ({dst.stat().st_size} bytes)")
    print("Done. Run: python examples/run_example.py")


if __name__ == "__main__":
    main()
