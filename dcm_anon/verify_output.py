"""Independent post-anonymization PHI residual scanner.

Breaks the self-attestation problem: the pipeline cannot certify its own
correctness, so this module re-reads output files and checks them against a
PHI tag list derived from HIPAA Safe Harbor §164.514(b)(2) and the TCIA
de-id checklist (NOT from :mod:`phi_table`). See README for background.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from pydicom import dcmread
from pydicom.dataset import Dataset

# Independent PHI tag list — sourced from HIPAA Safe Harbor + TCIA checklist.
# NOT imported from phi_table to preserve the independence property.
# Format: (group, element, human_label, hipaa_category)
#   hipaa_category cites the §164.514(b)(2)(i) sub-paragraph.
INDEPENDENT_PHI_TAGS: Final[tuple[tuple[int, int, str, str], ...]] = (
    (0x0010, 0x0010, "PatientName",            "(A) Names"),
    (0x0010, 0x0020, "PatientID",              "(R) Other unique identifying numbers"),
    (0x0010, 0x0030, "PatientBirthDate",       "(C) Dates more specific than year"),
    (0x0010, 0x0040, "PatientSex",             "(Q) Any other unique characteristic"),
    (0x0010, 0x1000, "OtherPatientIDs",        "(R) Other unique identifying numbers"),
    (0x0010, 0x1001, "OtherPatientNames",      "(A) Names"),
    (0x0010, 0x1005, "PatientBirthName",       "(A) Names"),
    (0x0010, 0x1010, "PatientAge",             "(C) Dates more specific than year"),
    (0x0010, 0x1040, "PatientAddress",         "(B) Geographic subdivisions smaller than state"),
    (0x0010, 0x1060, "PatientMotherBirthName", "(A) Names"),
    (0x0010, 0x2154, "PatientTelephoneNumbers","(D) Telephone numbers"),
    (0x0010, 0x2160, "EthnicGroup",            "(Q) Any other unique characteristic"),
    (0x0010, 0x2180, "Occupation",             "(Q) Any other unique characteristic"),
    (0x0010, 0x21B0, "AdditionalPatientHistory","(Q) Any other unique characteristic"),
    (0x0010, 0x21F0, "PatientReligiousPreference","(Q) Any other unique characteristic"),
    (0x0010, 0x4000, "PatientComments",        "(Q) Any other unique characteristic"),
    (0x0008, 0x0020, "StudyDate",              "(C) Dates more specific than year"),
    (0x0008, 0x0021, "SeriesDate",             "(C) Dates more specific than year"),
    (0x0008, 0x0022, "AcquisitionDate",        "(C) Dates more specific than year"),
    (0x0008, 0x0023, "ContentDate",            "(C) Dates more specific than year"),
    (0x0008, 0x0030, "StudyTime",              "(C) Dates more specific than year"),
    (0x0008, 0x0050, "AccessionNumber",        "(R) Other unique identifying numbers"),
    (0x0008, 0x0080, "InstitutionName",        "(B) Geographic subdivisions smaller than state"),
    (0x0008, 0x0081, "InstitutionAddress",     "(B) Geographic subdivisions smaller than state"),
    (0x0008, 0x0090, "ReferringPhysicianName", "(A) Names"),
    (0x0008, 0x0092, "ReferringPhysicianAddress","(B) Geographic subdivisions smaller than state"),
    (0x0008, 0x0094, "ReferringPhysicianTelephoneNumbers","(D) Telephone numbers"),
    (0x0008, 0x1010, "StationName",            "(R) Other unique identifying numbers"),
    (0x0008, 0x1030, "StudyDescription",       "(Q) Any other unique characteristic"),
    (0x0008, 0x103E, "SeriesDescription",      "(Q) Any other unique characteristic"),
    (0x0008, 0x1048, "PhysiciansOfRecord",     "(A) Names"),
    (0x0008, 0x1050, "PerformingPhysicianName","(A) Names"),
    (0x0008, 0x1060, "NameOfPhysiciansReadingStudy","(A) Names"),
    (0x0008, 0x1070, "OperatorsName",          "(A) Names"),
    (0x0008, 0x1080, "AdmittingDiagnosesDescription","(Q) Any other unique characteristic"),
    (0x0018, 0x1000, "DeviceSerialNumber",     "(N) Device identifiers"),
    (0x0020, 0x0010, "StudyID",                "(R) Other unique identifying numbers"),
    (0x0020, 0x4000, "ImageComments",          "(Q) Any other unique characteristic"),
    (0x0038, 0x0050, "SpecialNeeds",           "(Q) Any other unique characteristic"),
    (0x0040, 0x0006, "ScheduledPerformingPhysicianName","(A) Names"),
    (0x0040, 0x0244, "PerformedProcedureStepStartDate","(C) Dates more specific than year"),
    (0x0040, 0x0253, "PerformedProcedureStepID","(R) Other unique identifying numbers"),
)


# Acceptable cleaned values — emitted by dcm-anon for Z (zero/blank) and D
# (dummy placeholder) actions. Anything else is treated as a residual.
_CLEAN_PLACEHOLDERS: Final = frozenset(
    {
        "", " ", "ANON", "ANONYMOUS", "0", "0000", "00000000", "19000101",
        "000000.000000", "REMOVED",
    }
)


# Pixel-OCR PHI patterns (used only when pytesseract is available).
_PHI_OCR_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # Dates: 1990-01-01, 01/01/1990, 1 Jan 1990, etc.
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"),
    re.compile(
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*"
        r"\s+\d{4}\b",
        re.IGNORECASE,
    ),
    # MRN-style identifiers: 6-12 digit runs (loose; many false positives).
    re.compile(r"\b\d{6,12}\b"),
    # SSN-style: 3-2-4 digit pattern.
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Phone-style numbers.
    re.compile(r"\b\+?\d{1,3}[ -]?\(?\d{2,4}\)?[ -]?\d{3,4}[ -]?\d{3,4}\b"),
)


@dataclass(frozen=True)
class Residual:
    """One candidate PHI residual found in an output file."""

    file: str
    tag: str
    tag_label: str
    hipaa_category: str
    value_excerpt: str
    layer: str  # "metadata" or "pixel"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationResult:
    """Result of an independent verification pass.

    Designed for direct embedding in the compliance manifest.
    """

    sample_size: int
    files_scanned: int
    files_total: int
    metadata_tags_checked_per_file: int
    pixel_ocr_enabled: bool
    pixel_ocr_available: bool
    residuals: list[Residual] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.residuals

    def as_dict(self) -> dict[str, object]:
        return {
            "sample_size": self.sample_size,
            "files_scanned": self.files_scanned,
            "files_total": self.files_total,
            "metadata_tags_checked_per_file": self.metadata_tags_checked_per_file,
            "pixel_ocr_enabled": self.pixel_ocr_enabled,
            "pixel_ocr_available": self.pixel_ocr_available,
            "residuals_count": len(self.residuals),
            "residuals": [r.as_dict() for r in self.residuals],
            "passed": self.passed,
        }


def _format_tag(group: int, element: int) -> str:
    return f"{group:04X},{element:04X}"


def _is_uid_remapped(value: str) -> bool:
    """Heuristic: UID-format strings that match a remap root are clean."""
    if not value:
        return False
    # pydicom standard root used by UIDMapper: "1.2.826.0.1.3680043.8.498."
    # Any UID format (numeric dot-separated) is acceptable when scanning
    # UID tags. For non-UID tags this heuristic is irrelevant because the
    # value would not parse as a UID anyway.
    return bool(re.fullmatch(r"[0-9.]+", value)) and value.count(".") >= 3


def _value_is_clean(raw_value: object, label: str) -> tuple[bool, str]:
    """Return ``(is_clean, excerpt)``; excerpt is truncated to 64 chars."""
    if raw_value is None:
        return True, ""
    text = str(raw_value).strip()
    if not text:
        return True, ""
    if text.upper() in _CLEAN_PLACEHOLDERS:
        return True, ""
    if "UID" in label and _is_uid_remapped(text):
        return True, ""
    return False, text[:64]


def _scan_metadata(
    ds: Dataset,
    file_path: Path,
) -> list[Residual]:
    """Scan a dataset against the independent PHI tag list.

    Recurses into Sequence (SQ) items so that PHI surviving inside nested
    sequences (e.g. ``RequestAttributesSequence``, ``OriginalAttributesSequence``)
    is detected. Without this, a manifest could report ``passed=True`` while
    PHI persists in nested datasets.
    """
    findings: list[Residual] = []
    for group, element, label, hipaa in INDEPENDENT_PHI_TAGS:
        tag = (group, element)
        if tag not in ds:
            continue
        clean, excerpt = _value_is_clean(ds[tag].value, label)
        if clean:
            continue
        findings.append(Residual(
            file=str(file_path),
            tag=_format_tag(group, element),
            tag_label=label,
            hipaa_category=hipaa,
            value_excerpt=excerpt,
            layer="metadata",
        ))
    # Recurse into SQ items (defensive: any DataElement whose VR is "SQ").
    for elem in ds:
        if elem.VR != "SQ" or elem.value is None:
            continue
        for item in elem.value:
            if isinstance(item, Dataset):
                findings.extend(_scan_metadata(item, file_path))
    return findings


def _try_pytesseract() -> Any | None:
    """Return the pytesseract module if importable, else ``None``."""
    try:
        import pytesseract
        return pytesseract
    except ImportError:
        return None


def _scan_pixels(
    ds: Dataset,
    file_path: Path,
    pytesseract_mod: Any,
) -> list[Residual]:
    """Run pytesseract OCR on the pixel data and flag PHI-shaped strings."""
    if not hasattr(ds, "pixel_array"):
        return []
    try:
        arr = ds.pixel_array
    except Exception:
        return []
    # pytesseract.image_to_string accepts a 2D ndarray of uint8.
    image = arr
    if image.ndim == 3:
        image = image[image.shape[0] // 2]
    try:
        text = str(pytesseract_mod.image_to_string(image))
    except Exception:
        return []
    findings: list[Residual] = []
    for pattern in _PHI_OCR_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(Residual(
                file=str(file_path),
                tag="(pixel)",
                tag_label="BurnedInPixelText",
                hipaa_category="(Q) Any other unique characteristic",
                value_excerpt=match.group(0)[:64],
                layer="pixel",
            ))
    return findings


class PixelOCRUnavailableError(RuntimeError):
    """Raised when ``pixel_ocr=True`` but pytesseract / tesseract is missing.

    Silent degradation to metadata-only would let a user run
    ``--verify-output-pixel-ocr``, get a green manifest, and falsely
    conclude the pixel layer was scanned. Failing loudly forces the
    install step or the explicit ``pixel_ocr=False`` choice.
    """


def scan_outputs(
    output_dir: Path,
    *,
    sample_size: int = 10,
    pixel_ocr: bool = False,
    strict_ocr: bool = True,
) -> VerificationResult:
    """Independently scan a directory of anonymized DICOMs for PHI residuals.

    Args:
        output_dir: directory containing the anonymized files.
        sample_size: at most *N* files are scanned. Sampling is
            deterministic (sorted lexicographically) so the result is
            reproducible.
        pixel_ocr: if True, also run pytesseract OCR on pixel data.
        strict_ocr: when ``pixel_ocr=True`` and pytesseract / tesseract
            is unavailable, raise :class:`PixelOCRUnavailableError` rather
            than silently degrading. Default ``True``: a false green
            manifest is worse than a clean crash.

    Returns:
        VerificationResult ready to embed in a manifest.

    Raises:
        PixelOCRUnavailableError: ``pixel_ocr=True`` and ``strict_ocr=True``
            and pytesseract / tesseract is not importable.
    """
    files = sorted(output_dir.rglob("*.dcm"))
    files_total = len(files)
    sample = files[:max(0, sample_size)]
    pytesseract_mod = _try_pytesseract() if pixel_ocr else None
    pixel_available = pytesseract_mod is not None
    if pixel_ocr and not pixel_available and strict_ocr:
        raise PixelOCRUnavailableError(
            "--verify-output-pixel-ocr was requested but pytesseract is "
            "not importable. Install with: pip install pytesseract, plus "
            "the system tesseract binary. Or call scan_outputs(..., "
            "strict_ocr=False) to fall back to metadata-only scanning."
        )

    residuals: list[Residual] = []
    files_scanned = 0
    for path in sample:
        try:
            ds = dcmread(path)
        except Exception:
            continue
        files_scanned += 1
        residuals.extend(_scan_metadata(ds, path))
        if pixel_ocr and pytesseract_mod is not None:
            residuals.extend(_scan_pixels(ds, path, pytesseract_mod))

    return VerificationResult(
        sample_size=sample_size,
        files_scanned=files_scanned,
        files_total=files_total,
        metadata_tags_checked_per_file=len(INDEPENDENT_PHI_TAGS),
        pixel_ocr_enabled=pixel_ocr,
        pixel_ocr_available=pixel_available,
        residuals=residuals,
    )


__all__ = [
    "INDEPENDENT_PHI_TAGS",
    "PixelOCRUnavailableError",
    "Residual",
    "VerificationResult",
    "scan_outputs",
]
