"""Fail-closed safety gates.

A header de-identifier structurally CANNOT clear three high-risk channels, and
silently certifying them as clean is the worst failure mode (Cegedim-class false
assurance):

- **Burned-in pixel PHI** — name/DOB/MRN rendered into the pixels. The
  BurnedInAnnotation flag is optional and unreliable, so risk is driven off the
  modality / SOP Class, not the flag.
- **Recognizable face** — a head CT/MR reconstructs an identifiable face
  (Schwarz, NEJM 2019); metadata de-identification alone is insufficient.
- **Encapsulated documents** — the PDF/CDA byte stream is opaque to attribute
  scrubbing; its interior is never inspected.

When any of these is present and not explicitly waived, the tool must refuse to
report a clean / de-identified status (manifest FAILED + nonzero exit), pointing
the user at the right tool (pixel redaction, defacing) rather than emitting a
green manifest over residual PHI.
"""
from __future__ import annotations

from typing import Final

from pydicom.dataset import Dataset

RISK_BURNED_IN: Final = "burned_in_pixels"
RISK_FACE: Final = "recognizable_face"
RISK_ENCAPSULATED: Final = "encapsulated_document"

# Secondary Capture SOP Class family (screenshots / scanned docs / dose reports).
_SECONDARY_CAPTURE_PREFIX: Final = "1.2.840.10008.5.1.4.1.1.7"
_ENCAPSULATED_SOP_CLASSES: Final[frozenset[str]] = frozenset({
    "1.2.840.10008.5.1.4.1.1.104.1",  # Encapsulated PDF
    "1.2.840.10008.5.1.4.1.1.104.2",  # Encapsulated CDA
    "1.2.840.10008.5.1.4.1.1.104.3",  # Encapsulated STL
    "1.2.840.10008.5.1.4.1.1.104.4",  # Encapsulated OBJ
    "1.2.840.10008.5.1.4.1.1.104.5",  # Encapsulated MTL
})
_ENCAPSULATED_DOCUMENT_TAG: Final = 0x00420011
# Modalities whose pixels routinely carry burned-in PHI (flag unreliable).
_BURNED_IN_SUSPECT_MODALITIES: Final[frozenset[str]] = frozenset(
    {"US", "SC", "XC", "OT", "OAM", "GM", "ECG", "DOC"}
)
# Modalities that produce volumetric data from which a face can be reconstructed.
_FACE_MODALITIES: Final[frozenset[str]] = frozenset({"CT", "MR", "PT", "NM"})
_FACE_KEYWORDS: Final[tuple[str, ...]] = (
    "HEAD", "BRAIN", "SKULL", "FACE", "SINUS", "ORBIT", "TMJ", "IAC", "CRANI", "NEURO",
)


def _attr(ds: Dataset, name: str) -> str:
    return str(getattr(ds, name, "") or "")


def _sop_class(ds: Dataset) -> str:
    return _attr(ds, "SOPClassUID")


def has_burned_in_risk(ds: Dataset) -> bool:
    if _attr(ds, "BurnedInAnnotation").upper() == "YES":
        return True
    if _attr(ds, "Modality").upper() in _BURNED_IN_SUSPECT_MODALITIES:
        return True
    return _sop_class(ds).startswith(_SECONDARY_CAPTURE_PREFIX)


def has_face_risk(ds: Dataset) -> bool:
    if _attr(ds, "Modality").upper() not in _FACE_MODALITIES:
        return False
    haystack = " ".join(
        _attr(ds, a)
        for a in ("BodyPartExamined", "ProtocolName", "StudyDescription", "SeriesDescription")
    ).upper()
    return any(keyword in haystack for keyword in _FACE_KEYWORDS)


def has_encapsulated_document(ds: Dataset) -> bool:
    return _sop_class(ds) in _ENCAPSULATED_SOP_CLASSES or _ENCAPSULATED_DOCUMENT_TAG in ds


def detect_unresolved_risks(
    ds: Dataset,
    *,
    pixels_redacted: bool = False,
    face_cleaned: bool = False,
    allow_burned_in: bool = False,
    allow_face: bool = False,
    allow_encapsulated: bool = False,
) -> list[str]:
    """Return the unresolved fail-closed risks for *ds*. Evaluate on the ORIGINAL
    dataset (before scrubbing) so the modality / body-part signals still exist.
    """
    risks: list[str] = []
    if not allow_burned_in and not pixels_redacted and has_burned_in_risk(ds):
        risks.append(RISK_BURNED_IN)
    if not allow_face and not face_cleaned and has_face_risk(ds):
        risks.append(RISK_FACE)
    if not allow_encapsulated and has_encapsulated_document(ds):
        risks.append(RISK_ENCAPSULATED)
    return risks
