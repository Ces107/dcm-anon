"""Quick throughput microbenchmark for dcm-anon.

Generates synthetic DICOMs of varying size + count, times anonymize_path,
prints studies/sec and MB/sec. Run from repo root: python benchmarks/throughput.py.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from pydicom import Dataset, FileDataset
from pydicom.dataset import FileMetaDataset
from pydicom.uid import UID, ExplicitVRLittleEndian
from dcm_anon import AnonymizationConfig, anonymize_path

CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"


def make_synthetic_dcm(path: Path, payload_kb: int) -> None:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = UID(CT_SOP_CLASS)
    meta.MediaStorageSOPInstanceUID = UID(f"1.2.3.4.{path.stem}")
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.PatientName = "Synthetic^Patient"
    ds.PatientID = "PAT-0001"
    ds.PatientBirthDate = "19700101"
    ds.PatientSex = "O"
    ds.StudyDate = "20260519"
    ds.StudyInstanceUID = UID(f"1.2.3.5.{path.parent.name}")
    ds.SeriesInstanceUID = UID(f"1.2.3.6.{path.stem}")
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.Modality = "CT"
    ds.AccessionNumber = "ACC-1"
    ds.ReferringPhysicianName = "Doe^John"
    ds.AcquisitionDateTime = "20260519120000"
    ds.is_implicit_VR = False
    ds.is_little_endian = True
    side = max(1, int((payload_kb * 1024 / 2) ** 0.5))
    ds.PixelData = b"\0\1" * (side * side)
    ds.Rows = side
    ds.Columns = side
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.SamplesPerPixel = 1
    ds.save_as(path, write_like_original=False)


def bench(n_files: int, payload_kb: int, runs: int = 3) -> dict[str, float]:
    workdir = Path(tempfile.mkdtemp(prefix="dcm-anon-bench-"))
    try:
        src = workdir / "in"
        src.mkdir()
        for i in range(n_files):
            make_synthetic_dcm(src / f"{i:04d}.dcm", payload_kb)
        size_mb = sum(p.stat().st_size for p in src.iterdir()) / 1024 / 1024

        times: list[float] = []
        for _ in range(runs):
            dst = workdir / f"out_{time.time_ns()}"
            t0 = time.perf_counter()
            anonymize_path(src, dst, config=AnonymizationConfig())
            times.append(time.perf_counter() - t0)
            shutil.rmtree(dst)
        best = min(times)
        return {
            "n_files": n_files,
            "size_mb": size_mb,
            "best_s": best,
            "files_per_sec": n_files / best,
            "mb_per_sec": size_mb / best,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> None:
    print(f"{'n_files':>8} {'size_mb':>8} {'best_s':>8} {'files/s':>10} {'mb/s':>10}")
    print("-" * 50)
    for n, kb in [(10, 64), (50, 64), (100, 64), (10, 512), (10, 2048)]:
        r = bench(n, kb)
        print(
            f"{r['n_files']:>8} {r['size_mb']:>8.2f} {r['best_s']:>8.3f} "
            f"{r['files_per_sec']:>10.1f} {r['mb_per_sec']:>10.1f}"
        )


if __name__ == "__main__":
    main()
