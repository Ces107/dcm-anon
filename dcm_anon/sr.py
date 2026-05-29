"""DICOM Structured Report (SR) content-tree PHI scrubber.

This module owns ONLY the SR *content tree* — the recursive ContentSequence
(0040,A730) that Basic/Enhanced/Comprehensive SR objects (and KOS, mammography
CAD, RT structured content) use to carry free text, person names, dates and
UID references. Header-level identifiers (PatientName, ReferringPhysicianName,
the (0040,Axxx) SR header tags listed in ``phi_table.PHI_TAGS``) are owned by
the main pipeline and are intentionally untouched here.

The content tree is the residual-PHI channel the flat tag table cannot reach:
a TEXT node (0040,A160) can embed an SSN/email/MRN in prose; a PNAME node
(0040,A123) can name a referring clinician; a UIDREF node (0040,A124) must be
remapped consistently with the top-level UID remap or every cross-reference is
severed. PS3.15 calls scrubbing this tree the Clean Structured Content Option
(CID 7050 code 113104) — the operator writes that provenance code when this
module runs.

Dispatch is by ``ValueType`` (0040,A040), per PS3.3 Table C.17.3-8:
    TEXT, PNAME, DATE, TIME, DATETIME, CODE, NUM, UIDREF, COMPOSITE,
    IMAGE, WAVEFORM, SCOORD, SCOORD3D, TCOORD, CONTAINER.

Public API:
    has_sr_content(ds)            -> bool   (True if (0040,A730) present)
    scrub_sr_content(ds, mapper)  -> list[str]   (in-place; audit entries)
    SrConfig                       (frozen profile config dataclass)

Audit entries use the SAME ``"GGGG,EEEE:ACTION"`` format as
``pipeline._format_touch`` so they merge cleanly into ``AuditRecord.tags_modified``.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final

from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import UID

if TYPE_CHECKING:  # pragma: no cover
    from dcm_anon.uid_mapper import UIDMapper


# ---------------------------------------------------------------------------
# DICOM tag constants (group, element)
# ---------------------------------------------------------------------------

SR_CONTENT_SEQUENCE_TAG: Final[tuple[int, int]] = (0x0040, 0xA730)  # ContentSequence
SR_VALUE_TYPE_TAG: Final[tuple[int, int]] = (0x0040, 0xA040)        # ValueType
SR_TEXT_VALUE_TAG: Final[tuple[int, int]] = (0x0040, 0xA160)        # TextValue
SR_PERSON_NAME_TAG: Final[tuple[int, int]] = (0x0040, 0xA123)       # PersonName
SR_DATETIME_TAG: Final[tuple[int, int]] = (0x0040, 0xA120)          # DateTime
SR_DATE_TAG: Final[tuple[int, int]] = (0x0040, 0xA121)             # Date
SR_TIME_TAG: Final[tuple[int, int]] = (0x0040, 0xA122)             # Time
SR_UID_VALUE_TAG: Final[tuple[int, int]] = (0x0040, 0xA124)        # UID (UIDREF)
SR_OBSERVATION_DATETIME_TAG: Final[tuple[int, int]] = (0x0040, 0xA032)  # ObservationDateTime
SR_CONCEPT_NAME_CODE_SEQ_TAG: Final[tuple[int, int]] = (0x0040, 0xA043)  # ConceptNameCodeSequence


class SrAction(str, Enum):
    """Action codes this module records in the audit trail.

    ``str`` mixin keeps them JSON-serialisable and lets the operator merge them
    straight into ``AuditRecord.tags_modified`` alongside the PS3.15 codes.
    """

    REDACT_TEXT = "REDACT_TEXT"        # detected PHI spans replaced (default profile)
    BLANK_TEXT = "BLANK_TEXT"          # whole TextValue blanked (conservative profile)
    BLANK_PNAME = "BLANK_PNAME"        # PersonName blanked
    BLANK_DATETIME = "BLANK_DATETIME"  # DateTime blanked
    BLANK_DATE = "BLANK_DATE"          # Date blanked
    BLANK_TIME = "BLANK_TIME"          # Time blanked
    BLANK_OBS_DATETIME = "BLANK_OBS_DATETIME"  # ObservationDateTime blanked
    REMAP_UIDREF = "REMAP_UIDREF"      # UID remapped via shared UIDMapper


@dataclass(frozen=True)
class SrConfig:
    """Immutable configuration for an SR content-tree scrub.

    ``profile``
        ``"default"``       — TEXT nodes are scanned with the regex+blacklist
                              detector and only matched PHI spans are redacted;
                              clean prose is preserved.
        ``"conservative"``  — every TEXT node is blanked unconditionally
                              (free text is assumed to carry PHI).
    ``extra_blacklist``
        Additional whole-word tokens (case-insensitive) to redact in TEXT nodes
        under the ``default`` profile — e.g. a cohort's known surnames.
    """

    profile: str = "default"
    extra_blacklist: frozenset[str] = frozenset()

    @property
    def redact_all_text(self) -> bool:
        """True when the profile blanks all free text unconditionally."""
        return self.profile == "conservative"


# Recognised profile names — kept tiny and explicit (no Any-typed registry).
_VALID_PROFILES: Final[frozenset[str]] = frozenset({"default", "conservative"})


def _validate_profile(profile: str) -> None:
    if profile not in _VALID_PROFILES:
        valid = ", ".join(sorted(_VALID_PROFILES))
        raise ValueError(f"Unknown SR profile {profile!r}. Valid: {valid}")


# ---------------------------------------------------------------------------
# PHI regex detection (ported verbatim from dicom-sr-scrubber/phi_detect.py)
# ---------------------------------------------------------------------------

# (name, pattern). Order matters only for the human-readable label; overlaps
# are resolved by keeping the longest span in ``_redact_detected``.
_PHI_PATTERNS: Final[list[tuple[str, re.Pattern[str]]]] = [
    # US Social Security Number
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # MRN-like: keyword + digit run
    ("MRN_NUMERIC", re.compile(r"\bMRN[:\s#-]*\d{4,12}\b", re.IGNORECASE)),
    # Phone numbers (US-centric + international prefix)
    ("PHONE", re.compile(r"\b(?:\+?\d[\d\s\-().]{7,}\d)\b")),
    # Email addresses
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Free-text dates: MM/DD/YYYY, DD-MM-YYYY, YYYY-MM-DD
    ("DATE_MDY", re.compile(r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b")),
    # NPI (US National Provider Identifier) — keyword + 10 digits
    ("NPI", re.compile(r"\bNPI[:\s]*\d{10}\b", re.IGNORECASE)),
    # Spanish DNI / NIE
    ("DNI_NIE", re.compile(r"\b[0-9]{8}[A-Za-z]\b|\b[XYZ][0-9]{7}[A-Za-z]\b")),
    # French INS / NIR
    ("NIR", re.compile(r"\b[12]\s*\d{2}\s*\d{2}\s*\d{2}\s*\d{3}\s*\d{3}\s*\d{2}\b")),
    # German Versichertennummer (letter + 9 digits)
    ("VERSICHERTENNUMMER", re.compile(r"\b[A-Z]\d{9}\b")),
    # Accession-like (keyword + alnum)
    ("ACCESSION", re.compile(r"\bACC[:\s#-]*[A-Z0-9]{4,16}\b", re.IGNORECASE)),
]


@dataclass(frozen=True)
class _PhiSpan:
    """A single detected PHI span in a text value."""

    label: str
    start: int
    end: int


def _scan_regex(text: str) -> list[_PhiSpan]:
    spans: list[_PhiSpan] = []
    for name, pattern in _PHI_PATTERNS:
        for match in pattern.finditer(text):
            spans.append(_PhiSpan(label=name, start=match.start(), end=match.end()))
    return spans


def _scan_blacklist(text: str, blacklist: frozenset[str]) -> list[_PhiSpan]:
    if not blacklist:
        return []
    spans: list[_PhiSpan] = []
    for token in blacklist:
        stripped = token.strip()
        if not stripped:
            continue
        pattern = re.compile(r"\b" + re.escape(stripped) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            spans.append(_PhiSpan(label="BLACKLIST", start=match.start(), end=match.end()))
    return spans


def _dedupe_spans(spans: list[_PhiSpan]) -> list[_PhiSpan]:
    """Drop shorter overlapping spans, keeping the longest at each position."""
    if not spans:
        return spans
    ordered = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    result: list[_PhiSpan] = []
    last_end = -1
    for span in ordered:
        if span.start >= last_end:
            result.append(span)
            last_end = span.end
    return result


def detect_phi_spans(text: str, extra_blacklist: frozenset[str] = frozenset()) -> list[_PhiSpan]:
    """Return de-overlapped PHI spans (regex + optional blacklist) in *text*."""
    spans = _scan_regex(text) + _scan_blacklist(text, extra_blacklist)
    return _dedupe_spans(spans)


def _redact_detected(text: str, extra_blacklist: frozenset[str]) -> str:
    """Replace each detected PHI span with ``[REDACTED:<label>]``.

    Returns the input unchanged when nothing is detected.
    """
    spans = detect_phi_spans(text, extra_blacklist)
    if not spans:
        return text
    ordered = sorted(spans, key=lambda s: s.start)
    out: list[str] = []
    cursor = 0
    for span in ordered:
        if span.start < cursor:
            continue
        out.append(text[cursor : span.start])
        out.append(f"[REDACTED:{span.label}]")
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Tree walking + per-ValueType scrubbing
# ---------------------------------------------------------------------------


def has_sr_content(ds: Dataset) -> bool:
    """True if *ds* carries an SR content tree (a non-empty ContentSequence)."""
    return _content_sequence(ds) is not None


def _content_sequence(ds: Dataset) -> Sequence | None:
    """Return the ContentSequence at (0040,A730) or None if absent/empty."""
    elem = ds.get(SR_CONTENT_SEQUENCE_TAG)
    if elem is None:
        return None
    value = elem.value
    if not isinstance(value, Sequence) or len(value) == 0:
        return None
    return value


def _value_type(item: Dataset) -> str:
    elem = item.get(SR_VALUE_TYPE_TAG)
    if elem is None:
        return "UNKNOWN"
    return str(elem.value).strip().upper()


def _iter_items(ds: Dataset) -> Iterator[Dataset]:
    """Yield every content item in the tree rooted at *ds*, depth-first.

    Each ContentSequence item is yielded once; nested ContentSequences are
    recursed into. The root dataset itself is NOT yielded (its top-level
    text/date nodes are handled separately by ``_scrub_root_nodes``).
    """
    seq = _content_sequence(ds)
    if seq is None:
        return
    for item in seq:
        yield item
        yield from _iter_items(item)


def _blank_str_element(item: Dataset, tag: tuple[int, int]) -> bool:
    """Blank a string-valued element to "" if present and non-empty. Returns
    True if a change was made."""
    elem = item.get(tag)
    if elem is None:
        return False
    if elem.value in (None, ""):
        return False
    elem.value = ""
    return True


def _scrub_text_node(item: Dataset, config: SrConfig) -> str | None:
    """Scrub a TEXT node's TextValue. Returns the action label or None."""
    elem = item.get(SR_TEXT_VALUE_TAG)
    if elem is None or elem.value in (None, ""):
        return None
    if config.redact_all_text:
        elem.value = ""
        return SrAction.BLANK_TEXT.value
    original = str(elem.value)
    redacted = _redact_detected(original, config.extra_blacklist)
    if redacted == original:
        return None
    elem.value = redacted
    return SrAction.REDACT_TEXT.value


def _scrub_uidref_node(item: Dataset, mapper: UIDMapper) -> str | None:
    """Remap a UIDREF node's UID via the shared mapper. Returns label or None."""
    elem = item.get(SR_UID_VALUE_TAG)
    if elem is None or elem.value in (None, ""):
        return None
    original = str(elem.value)
    elem.value = UID(mapper.remap(original))
    return SrAction.REMAP_UIDREF.value


def _scrub_item(item: Dataset, mapper: UIDMapper, config: SrConfig) -> list[str]:
    """Apply the per-ValueType rule to a single content item in-place.

    Returns audit entries in ``"GGGG,EEEE:ACTION"`` form.
    """
    value_type = _value_type(item)
    touched: list[str] = []

    if value_type == "TEXT":
        action = _scrub_text_node(item, config)
        if action is not None:
            touched.append(_format(SR_TEXT_VALUE_TAG, action))
    elif value_type == "PNAME":
        if _blank_str_element(item, SR_PERSON_NAME_TAG):
            touched.append(_format(SR_PERSON_NAME_TAG, SrAction.BLANK_PNAME.value))
    elif value_type == "DATETIME":
        if _blank_str_element(item, SR_DATETIME_TAG):
            touched.append(_format(SR_DATETIME_TAG, SrAction.BLANK_DATETIME.value))
    elif value_type == "DATE":
        if _blank_str_element(item, SR_DATE_TAG):
            touched.append(_format(SR_DATE_TAG, SrAction.BLANK_DATE.value))
    elif value_type == "TIME":
        if _blank_str_element(item, SR_TIME_TAG):
            touched.append(_format(SR_TIME_TAG, SrAction.BLANK_TIME.value))
    elif value_type == "UIDREF":
        action = _scrub_uidref_node(item, mapper)
        if action is not None:
            touched.append(_format(SR_UID_VALUE_TAG, action))
    # CODE / NUM / CONTAINER / IMAGE / WAVEFORM / SCOORD / TCOORD / COMPOSITE:
    # no value-level PHI in the content tree; structure is recursed by the walker.

    # ObservationDateTime (0040,A032) can appear on any item regardless of its
    # ValueType — blank it everywhere.
    if _blank_str_element(item, SR_OBSERVATION_DATETIME_TAG):
        touched.append(_format(SR_OBSERVATION_DATETIME_TAG, SrAction.BLANK_OBS_DATETIME.value))

    return touched


def _scrub_root_nodes(ds: Dataset, mapper: UIDMapper, config: SrConfig) -> list[str]:
    """Scrub value attributes that may sit on the SR ROOT dataset itself.

    The root SR document node carries its own ValueType/value attributes
    (commonly a CONTAINER, but a top-level TextValue/Date/Time/ObservationDateTime
    is permitted). The flat PHI table handles the SR *header* identifier tags;
    here we cover root-level *content* value attributes the table does not list
    as content-tree members.
    """
    touched: list[str] = []
    # Root TextValue (rare but valid on a root TEXT document).
    text_action = _scrub_text_node(ds, config)
    if text_action is not None:
        touched.append(_format(SR_TEXT_VALUE_TAG, text_action))
    # Root Date/Time/DateTime content values.
    if _blank_str_element(ds, SR_DATETIME_TAG):
        touched.append(_format(SR_DATETIME_TAG, SrAction.BLANK_DATETIME.value))
    if _blank_str_element(ds, SR_DATE_TAG):
        touched.append(_format(SR_DATE_TAG, SrAction.BLANK_DATE.value))
    if _blank_str_element(ds, SR_TIME_TAG):
        touched.append(_format(SR_TIME_TAG, SrAction.BLANK_TIME.value))
    if _blank_str_element(ds, SR_OBSERVATION_DATETIME_TAG):
        touched.append(_format(SR_OBSERVATION_DATETIME_TAG, SrAction.BLANK_OBS_DATETIME.value))
    return touched


def scrub_sr_content(
    ds: Dataset,
    mapper: UIDMapper,
    config: SrConfig | None = None,
) -> list[str]:
    """Scrub PHI from an SR content tree IN-PLACE on the loaded dataset.

    Walks ContentSequence (0040,A730) recursively, dispatching by ValueType
    (0040,A040): TEXT redacted/blanked, PNAME blanked, DATE/TIME/DATETIME and
    ObservationDateTime blanked, UIDREF remapped through the SHARED *mapper* so
    SR UID references match the top-level UID remap. Header tags (PatientName,
    the (0040,Axxx) header identifiers) are NOT touched — those belong to the
    main pipeline.

    Returns audit entries in the ``"GGGG,EEEE:ACTION"`` format used by
    ``pipeline._format_touch`` (e.g. ``"0040,A160:REDACT_TEXT"``). An empty list
    means the dataset had no content tree or no content-level PHI was found.
    """
    cfg = config if config is not None else SrConfig()
    _validate_profile(cfg.profile)

    touched: list[str] = _scrub_root_nodes(ds, mapper, cfg)
    for item in _iter_items(ds):
        touched.extend(_scrub_item(item, mapper, cfg))
    return touched


def _format(tag: tuple[int, int], action: str) -> str:
    """Render a touch entry identically to ``pipeline._format_touch``."""
    return f"{tag[0]:04X},{tag[1]:04X}:{action}"


__all__ = [
    "SR_CONTENT_SEQUENCE_TAG",
    "SR_UID_VALUE_TAG",
    "SR_VALUE_TYPE_TAG",
    "SrAction",
    "SrConfig",
    "detect_phi_spans",
    "has_sr_content",
    "scrub_sr_content",
]
