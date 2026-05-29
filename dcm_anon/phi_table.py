"""PS3.15 E.1-1 tag table. Action semantics in actions.py."""
from __future__ import annotations

from typing import Final

from dcm_anon.actions import Action

PHI_TAGS: Final[dict[tuple[int, int], Action]] = {
    # ---- Instance / study / series UIDs ------------------------------------
    # NOTE: (0x0002, 0x0003) — Media Storage SOP Instance UID — intentionally
    # NOT listed here. It lives in file_meta, not the main dataset, and is
    # handled separately by ``pipeline._maintain_file_meta_consistency``.
    (0x0008, 0x0014): Action.U,   # Instance Creator UID
    (0x0008, 0x0017): Action.U,   # Acquisition UID
    (0x0008, 0x0018): Action.U,   # SOP Instance UID
    (0x0008, 0x0019): Action.U,   # Pyramid UID
    (0x0008, 0x1155): Action.U,   # Referenced SOP Instance UID
    (0x0008, 0x1195): Action.U,   # Transaction UID
    (0x0008, 0x3010): Action.U,   # Irradiation Event UID
    (0x0018, 0x1002): Action.U,   # Device UID
    (0x0018, 0x100B): Action.U,   # Manufacturer's Device Class UID
    (0x0020, 0x000D): Action.U,   # Study Instance UID
    (0x0020, 0x000E): Action.U,   # Series Instance UID
    (0x0020, 0x0052): Action.U,   # Frame of Reference UID
    (0x0020, 0x0200): Action.U,   # Synchronization Frame of Reference UID
    (0x0020, 0x9161): Action.U,   # Concatenation UID
    (0x0020, 0x9164): Action.U,   # Dimension Organization UID
    (0x0028, 0x1199): Action.U,   # Palette Color Lookup Table UID
    (0x0028, 0x1214): Action.U,   # Large Palette Color Lookup Table UID
    (0x0040, 0xA124): Action.U,   # UID (SR)
    (0x0040, 0xA171): Action.U,   # Observation UID
    (0x0070, 0x031A): Action.U,   # Fiducial UID
    (0x0070, 0x1101): Action.U,   # Presentation Display Collection UID
    (0x0070, 0x1102): Action.U,   # Presentation Sequence Collection UID
    (0x3010, 0x0006): Action.U,   # Conceptual Volume UID
    (0x3010, 0x0013): Action.U,   # Constituent Conceptual Volume UID
    (0x300A, 0x0013): Action.U,   # Dose Reference UID
    (0x300A, 0x0650): Action.U,   # Patient Setup UID
    (0x003A, 0x0310): Action.U,   # Multiplex Group UID
    # ---- Patient identifiers -----------------------------------------------
    (0x0010, 0x0010): Action.Z,   # Patient's Name
    (0x0010, 0x0020): Action.Z,   # Patient ID
    (0x0010, 0x0030): Action.Z,   # Patient's Birth Date
    (0x0010, 0x0032): Action.X,   # Patient's Birth Time
    (0x0010, 0x0040): Action.Z,   # Patient's Sex
    (0x0010, 0x0050): Action.X,   # Patient's Insurance Plan Code Sequence
    (0x0010, 0x1000): Action.X,   # Other Patient IDs
    (0x0010, 0x1001): Action.X,   # Other Patient Names
    (0x0010, 0x1002): Action.X,   # Other Patient IDs Sequence
    (0x0010, 0x1010): Action.X,   # Patient's Age
    (0x0010, 0x1020): Action.X,   # Patient's Size
    (0x0010, 0x1030): Action.X,   # Patient's Weight
    (0x0010, 0x1040): Action.X,   # Patient's Address
    (0x0010, 0x1050): Action.X,   # Insurance Plan Identification
    (0x0010, 0x1060): Action.X,   # Patient's Mother's Birth Name
    (0x0010, 0x1080): Action.X,   # Military Rank
    (0x0010, 0x1081): Action.X,   # Branch of Service
    (0x0010, 0x1090): Action.X,   # Medical Record Locator
    (0x0010, 0x2000): Action.X,   # Medical Alerts
    (0x0010, 0x2110): Action.X,   # Allergies
    (0x0010, 0x2150): Action.X,   # Country of Residence
    (0x0010, 0x2154): Action.X,   # Patient's Telephone Numbers
    (0x0010, 0x2155): Action.X,   # Patient's Telecom Information
    (0x0010, 0x0034): Action.X,   # Patient's Death Date in Alternative Calendar
    (0x0010, 0x0035): Action.X,   # Patient's Alternative Calendar
    (0x0010, 0x1005): Action.X,   # Patient's Birth Name
    (0x0010, 0x2160): Action.X,   # Ethnic Group
    (0x0010, 0x2180): Action.X,   # Occupation
    (0x0010, 0x21B0): Action.X,   # Additional Patient History
    (0x0010, 0x21C0): Action.X,   # Pregnancy Status
    (0x0010, 0x21D0): Action.X,   # Last Menstrual Date
    (0x0010, 0x21F0): Action.X,   # Patient's Religious Preference
    (0x0010, 0x2203): Action.X,   # Patient's Sex Neutered
    (0x0010, 0x4000): Action.X,   # Patient Comments
    # ---- Study / order information -----------------------------------------
    (0x0008, 0x0020): Action.X,   # Study Date
    (0x0008, 0x0021): Action.X,   # Series Date
    (0x0008, 0x0022): Action.X,   # Acquisition Date
    (0x0008, 0x002A): Action.X,   # Acquisition DateTime
    (0x0008, 0x0023): Action.Z,   # Content Date
    (0x0008, 0x0030): Action.X,   # Study Time
    (0x0008, 0x0031): Action.X,   # Series Time
    (0x0008, 0x0032): Action.X,   # Acquisition Time
    (0x0008, 0x0033): Action.Z,   # Content Time
    (0x0008, 0x0050): Action.Z,   # Accession Number
    (0x0008, 0x0080): Action.X,   # Institution Name
    (0x0008, 0x0081): Action.X,   # Institution Address
    (0x0008, 0x0082): Action.X,   # Institution Code Sequence
    (0x0008, 0x0090): Action.Z,   # Referring Physician's Name
    (0x0008, 0x0092): Action.X,   # Referring Physician's Address
    (0x0008, 0x0094): Action.X,   # Referring Physician's Telephone Numbers
    (0x0008, 0x0096): Action.X,   # Referring Physician Identification Sequence
    (0x0008, 0x009C): Action.Z,   # Consulting Physician's Name
    (0x0008, 0x009D): Action.X,   # Consulting Physician Identification Sequence
    (0x0008, 0x1010): Action.X,   # Station Name
    (0x0008, 0x1030): Action.X,   # Study Description
    (0x0008, 0x103E): Action.X,   # Series Description
    (0x0008, 0x1040): Action.X,   # Institutional Department Name
    (0x0008, 0x1041): Action.X,   # Institutional Department Type Code Sequence
    (0x0008, 0x1048): Action.X,   # Physician(s) of Record
    (0x0008, 0x1049): Action.X,   # Physician(s) of Record Identification Sequence
    (0x0008, 0x1050): Action.X,   # Performing Physician's Name
    (0x0008, 0x1052): Action.X,   # Performing Physician Identification Sequence
    (0x0008, 0x1060): Action.X,   # Name of Physician(s) Reading Study
    (0x0008, 0x1062): Action.X,   # Physician(s) Reading Study Identification Sequence
    (0x0008, 0x1070): Action.X,   # Operators' Name
    (0x0008, 0x1072): Action.X,   # Operator Identification Sequence
    (0x0008, 0x1080): Action.X,   # Admitting Diagnoses Description
    (0x0008, 0x1084): Action.X,   # Admitting Diagnoses Code Sequence
    (0x0008, 0x1111): Action.X,   # Referenced Performed Procedure Step Sequence
    (0x0008, 0x1115): Action.X,   # Referenced Series Sequence
    (0x0008, 0x4000): Action.X,   # Identifying Comments
    (0x0018, 0x1000): Action.X,   # Device Serial Number
    (0x0018, 0x1004): Action.X,   # Plate ID
    (0x0018, 0x1005): Action.X,   # Generator ID
    (0x0018, 0x1007): Action.X,   # Cassette ID
    (0x0018, 0x1008): Action.X,   # Gantry ID
    (0x0018, 0x1030): Action.X,   # Protocol Name
    (0x0018, 0x4000): Action.X,   # Acquisition Comments
    (0x0018, 0x9424): Action.X,   # Acquisition Protocol Description
    (0x0020, 0x0010): Action.Z,   # Study ID
    (0x0020, 0x0027): Action.X,   # Pyramid Label
    (0x0020, 0x4000): Action.X,   # Image Comments
    (0x0040, 0x0006): Action.X,   # Scheduled Performing Physician's Name
    (0x0040, 0x0244): Action.X,   # Performed Procedure Step Start Date
    (0x0040, 0x0245): Action.X,   # Performed Procedure Step Start Time
    (0x0040, 0x0250): Action.X,   # Performed Procedure Step End Date
    (0x0040, 0x0251): Action.X,   # Performed Procedure Step End Time
    (0x0040, 0x0253): Action.X,   # Performed Procedure Step ID
    (0x0040, 0x0254): Action.X,   # Performed Procedure Step Description
    (0x0040, 0x0275): Action.X,   # Request Attributes Sequence
    (0x0040, 0x0280): Action.X,   # Comments on the Performed Procedure Step
    (0x0040, 0x1004): Action.X,   # Patient Transport Arrangements
    (0x0040, 0x2001): Action.X,   # Reason for the Imaging Service Request
    (0x0040, 0x2004): Action.X,   # Issue Date of Imaging Service Request
    (0x0040, 0x2005): Action.X,   # Issue Time of Imaging Service Request
    (0x0040, 0x2008): Action.X,   # Order Entered By
    (0x0040, 0x2009): Action.X,   # Order Enterer's Location
    (0x0040, 0x2400): Action.X,   # Imaging Service Request Comments
    (0x0040, 0xA123): Action.X,   # Person Name (SR)
    (0x0040, 0xA07A): Action.X,   # Participant Sequence
    # ---- Admission / location / presentation -------------------------------
    (0x0038, 0x0010): Action.X,   # Admission ID
    (0x0038, 0x0020): Action.X,   # Admitting Date
    (0x0038, 0x0021): Action.X,   # Admitting Time
    (0x0038, 0x0300): Action.X,   # Current Patient Location
    (0x0070, 0x0084): Action.X,   # Content Creator's Name (Presentation State)
    (0x0070, 0x0086): Action.X,   # Content Creator Identification Code Sequence
    # ---- Original-Attributes audit trail (P0 — PACS coercion leak risk) ----
    (0x0400, 0x0561): Action.X,   # Original Attributes Sequence (PS3.15 mandates X)
    # ---- Retired tags still seen in practice -------------------------------
    (0x0008, 0x0024): Action.X,   # Overlay Date (RET)
    (0x0008, 0x0025): Action.X,   # Curve Date (RET)
    (0x0008, 0x0034): Action.X,   # Overlay Time (RET)
    (0x0008, 0x0035): Action.X,   # Curve Time (RET)
    (0x0020, 0x0030): Action.X,   # Image Position (RET)
    (0x0020, 0x1070): Action.X,   # Other Study Numbers (RET)
    (0x4008, 0x010C): Action.X,   # Interpretation Author (RET)
    (0x4008, 0x0111): Action.X,   # Interpretation Approver Sequence (RET)
    (0x4008, 0x0300): Action.X,   # Impressions (RET)
    # ---- v0.6.0 completeness sweep: identifiers absent from the prior table -
    # (named explicitly in the v0.6.0 audit as surviving verbatim). The blanket
    # PN-VR sweep in pipeline catches person-names generally; these are the
    # non-PN / free-text / id identifiers that the sweep does not reach.
    (0x0008, 0x0201): Action.X,   # Timezone Offset From UTC
    (0x0010, 0x0021): Action.X,   # Issuer of Patient ID
    (0x0010, 0x2297): Action.X,   # Responsible Person (PN)
    (0x0010, 0x2298): Action.X,   # Responsible Person Role
    (0x0010, 0x2299): Action.X,   # Responsible Organization
    (0x0032, 0x1032): Action.X,   # Requesting Physician (PN)
    (0x0032, 0x1033): Action.X,   # Requesting Service
    (0x0032, 0x1060): Action.X,   # Requested Procedure Description (free text)
    (0x0032, 0x1066): Action.X,   # Reason for Visit
    (0x0032, 0x1070): Action.X,   # Requested Contrast Agent
    (0x0032, 0x4000): Action.X,   # Study Comments (RET)
    (0x0038, 0x0050): Action.X,   # Special Needs
    (0x0038, 0x0060): Action.X,   # Service Episode ID
    (0x0038, 0x0062): Action.X,   # Service Episode Description
    (0x0038, 0x0400): Action.X,   # Patient's Institution Residence
    (0x0038, 0x0500): Action.X,   # Patient State
    (0x0038, 0x4000): Action.X,   # Visit Comments
    (0x0040, 0x1010): Action.X,   # Names of Intended Recipients of Results (PN)
    (0x0040, 0x1400): Action.X,   # Requested Procedure Comments
    (0x0040, 0x2010): Action.X,   # Order Callback Phone Number
    (0x0040, 0x2011): Action.X,   # Order Callback Telecom Information
    (0x0040, 0xA073): Action.X,   # Verifying Observer Sequence (SR)
    (0x0040, 0xA075): Action.X,   # Verifying Observer Name (SR, PN)
    (0x0040, 0xA078): Action.X,   # Author Observer Sequence (SR)
    (0x0040, 0xA088): Action.X,   # Verifying Observer Identification Code Sequence
    (0x0100, 0x0420): Action.X,   # SOP Authorization DateTime
    (0x3006, 0x0026): Action.X,   # ROI Name (RT)
    (0x3006, 0x0028): Action.X,   # ROI Description (RT)
    (0x3006, 0x0085): Action.X,   # ROI Observation Label (RT)
    (0x300E, 0x0008): Action.X,   # Reviewer Name (RT, PN)
    (0x4008, 0x0114): Action.X,   # Physician Approving Interpretation (RET, PN)
    (0x4008, 0x0118): Action.X,   # Distribution Name (RET, PN)
    (0x4008, 0x0119): Action.X,   # Distribution Address (RET)
}

# Tags whose Z-action requires a non-empty placeholder per their VR.
PLACEHOLDERS: Final[dict[tuple[int, int], object]] = {
    (0x0008, 0x0023): "19000101",      # Content Date (DA)
    (0x0008, 0x0033): "000000.000000",  # Content Time (TM)
    (0x0008, 0x0050): "",               # Accession Number
    (0x0008, 0x0090): "",               # Referring Physician's Name (PN)
    (0x0008, 0x009C): "",               # Consulting Physician's Name (PN)
    (0x0010, 0x0010): "ANON",           # Patient's Name
    (0x0010, 0x0020): "0",              # Patient ID
    (0x0010, 0x0030): "19000101",       # Patient's Birth Date (DA)
    (0x0010, 0x0040): "",               # Patient's Sex (CS)
    (0x0020, 0x0010): "0",              # Study ID
}

# Tags that receive a STABLE PER-PATIENT pseudonym (not a shared constant) when
# a salt is set, so distinct patients stay distinct in the output while remaining
# unlinkable to the source without the salt. Without a salt they fall back to the
# PLACEHOLDERS constants above (which collapse all patients — cohort separation
# is lost; the CLI/docs warn about this).
PSEUDONYMIZE_TAGS: Final[frozenset[tuple[int, int]]] = frozenset({
    (0x0010, 0x0010),  # Patient's Name
    (0x0010, 0x0020),  # Patient ID
})

BURNED_IN_TAG: Final[tuple[int, int]] = (0x0028, 0x0301)

# Curve / Overlay group ranges scrubbed wholesale.
CURVE_GROUP_MASK: Final[int] = 0xFF00
CURVE_GROUPS: Final[frozenset[int]] = frozenset({0x5000, 0x6000})
