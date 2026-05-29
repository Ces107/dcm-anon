"""PS3.15 de-identification provenance: the attributes a conformant tool MUST
write so the output self-identifies as de-identified, and the CID 7050
De-identification Method codes.

PS3.15 E.1.1 requires Patient Identity Removed (0012,0062) = "YES" and, when
asserting a profile/option, one or more CID 7050 codes in De-identification
Method Code Sequence (0012,0064) and/or free text in De-identification Method
(0012,0063). Recording a code for a pass that did NOT run is false provenance —
so codes are emitted ONLY for options actually executed this run.
"""
from __future__ import annotations

from typing import Final

from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

MethodCode = tuple[str, str]  # (Code Value, Code Meaning), Coding Scheme = "DCM"

# CID 7050 — De-identification Method (verified against PS3.16 CID 7050).
BASIC_PROFILE: Final[MethodCode] = ("113100", "Basic Application Confidentiality Profile")
CLEAN_PIXEL_DATA: Final[MethodCode] = ("113101", "Clean Pixel Data Option")
CLEAN_RECOGNIZABLE_VISUAL_FEATURES: Final[MethodCode] = (
    "113102", "Clean Recognizable Visual Features Option",
)
CLEAN_GRAPHICS: Final[MethodCode] = ("113103", "Clean Graphics Option")
CLEAN_STRUCTURED_CONTENT: Final[MethodCode] = ("113104", "Clean Structured Content Option")
CLEAN_DESCRIPTORS: Final[MethodCode] = ("113105", "Clean Descriptors Option")
RETAIN_FULL_DATES: Final[MethodCode] = (
    "113106", "Retain Longitudinal Temporal Information Full Dates Option",
)
RETAIN_MODIFIED_DATES: Final[MethodCode] = (
    "113107", "Retain Longitudinal Temporal Information Modified Dates Option",
)
RETAIN_PATIENT_CHARACTERISTICS: Final[MethodCode] = (
    "113108", "Retain Patient Characteristics Option",
)
RETAIN_DEVICE_IDENTITY: Final[MethodCode] = ("113109", "Retain Device Identity Option")
RETAIN_UIDS: Final[MethodCode] = ("113110", "Retain UIDs Option")
RETAIN_SAFE_PRIVATE: Final[MethodCode] = ("113111", "Retain Safe Private Option")
RETAIN_INSTITUTION_IDENTITY: Final[MethodCode] = (
    "113112", "Retain Institution Identity Option",
)


def write_deid_provenance(
    ds: Dataset,
    tool_version: str,
    *,
    keep_private: bool = False,
    extra_codes: list[MethodCode] | None = None,
) -> list[str]:
    """Write (0012,0062)/(0012,0063)/(0012,0064) onto *ds* reflecting ONLY what
    actually ran. Call AFTER scrubbing so the attributes are not themselves
    removed. Returns audit-trail entries.

    With ``keep_private`` the run is NOT Basic-Profile conformant (the profile
    mandates private removal), so the Basic Profile code is NOT emitted — the
    free-text method states the deviation plainly rather than over-claiming.
    """
    codes: list[MethodCode] = []
    # (0012,0063) DeidentificationMethod is VR LO (<=64 chars per value) but
    # VM 1-n, so use a multi-valued list with each value within the limit.
    if keep_private:
        method_text = [
            "PS3.15 Basic Profile actions; private attributes RETAINED",
            "NOT Basic Profile conformant (--keep-private)",
            f"dcm-anon {tool_version}",
        ]
    else:
        codes.append(BASIC_PROFILE)
        method_text = [
            "DICOM PS3.15 Basic Application Confidentiality Profile",
            f"dcm-anon {tool_version}",
        ]
    if extra_codes:
        codes.extend(extra_codes)

    ds.PatientIdentityRemoved = "YES"        # (0012,0062)
    ds.DeidentificationMethod = method_text  # (0012,0063)

    if codes:
        seq = Sequence()
        for code_value, code_meaning in codes:
            item = Dataset()
            item.CodeValue = code_value                  # (0008,0100)
            item.CodingSchemeDesignator = "DCM"          # (0008,0102)
            item.CodeMeaning = code_meaning              # (0008,0104)
            seq.append(item)
        ds.DeidentificationMethodCodeSequence = seq      # (0012,0064)

    touched = ["0012,0062:provenance(YES)", "0012,0063:provenance"]
    if codes:
        touched.append(f"0012,0064:provenance({'+'.join(c for c, _ in codes)})")
    return touched
