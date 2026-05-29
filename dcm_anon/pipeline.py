"""Anonymization pipeline: composes phi_table, actions, uid_mapper, and audit."""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydicom import dcmread
from pydicom.dataset import Dataset

from dcm_anon.actions import DEFAULT_REGISTRY, Action, ActionRegistry
from dcm_anon.audit import (
    AuditRecord,
    AuditSummary,
    ProcessingError,
    audit_sha256,
    utc_now_iso,
)
from dcm_anon.phi_table import BURNED_IN_TAG, CURVE_GROUP_MASK, CURVE_GROUPS, PHI_TAGS
from dcm_anon.uid_mapper import UIDMapper

LOG = logging.getLogger("dcmanon")

ProgressCallback = Callable[[int, int, Path], None]
TagSet = frozenset[tuple[int, int]]


@dataclass(frozen=True)
class AnonymizationConfig:
    """Bundle of options for a full :func:`anonymize_path` invocation."""

    salt: str | None = None
    dry_run: bool = False
    continue_on_error: bool = False
    keep_tags: TagSet = field(default_factory=frozenset)
    keep_private: bool = False
    progress_cb: ProgressCallback | None = None
    registry: ActionRegistry = field(default_factory=lambda: DEFAULT_REGISTRY)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_burned_in_phi(ds: Dataset) -> bool:
    burned = ds.get(BURNED_IN_TAG)
    return burned is not None and str(burned.value).upper() == "YES"


def parse_keep_tag(spec: str) -> tuple[int, int]:
    """Parse ``"GGGG,EEEE"`` (hex) into a ``(group, element)`` tag tuple."""
    cleaned = spec.strip().lstrip("(").rstrip(")")
    parts = cleaned.split(",")
    if len(parts) != 2:
        raise ValueError(f"keep-tag spec must be 'GGGG,EEEE' hex (got {spec!r})")
    group_str, elem_str = (p.strip() for p in parts)
    try:
        return (int(group_str, 16), int(elem_str, 16))
    except ValueError as exc:
        raise ValueError(f"keep-tag spec must be hex digits (got {spec!r})") from exc


def _apply_point_actions(
    ds: Dataset,
    keep: TagSet,
    mapper: UIDMapper,
    registry: ActionRegistry,
) -> list[str]:
    touched: list[str] = []
    for tag, action in PHI_TAGS.items():
        if tag in keep or tag not in ds:
            continue
        registry[action](ds, tag, mapper)
        touched.append(_format_touch(tag, action.value))
    return touched


def _scrub_curve_overlay_ranges(ds: Dataset, keep: TagSet) -> list[str]:
    touched: list[str] = []
    range_tags = [
        t for t in list(ds.keys())
        if t.group & CURVE_GROUP_MASK in CURVE_GROUPS
    ]
    for tag in range_tags:
        pair = (tag.group, tag.element)
        if pair in keep:
            continue
        del ds[tag]
        touched.append(_format_touch(pair, "X(range)"))
    return touched


def _strip_private_elements(ds: Dataset, keep: TagSet) -> list[str]:
    """Remove every private (odd-group) data element, including private-creator
    reservation elements. PS3.15 Basic Profile mandates action X on all private
    attributes — vendors (Siemens CSA 0029, GE 0009/0019, Philips 2001/2005)
    routinely store patient name / accession / raw acquisition data there.
    Retention is the opt-in exception (--keep-private), never the default.
    Operates at one dataset level; nested private SQs are reached via recursion.
    """
    touched: list[str] = []
    for elem in list(ds):
        tag = elem.tag
        if not tag.is_private:
            continue
        pair = (tag.group, tag.element)
        if pair in keep:
            continue
        del ds[tag]
        touched.append(_format_touch(pair, "X(private)"))
    return touched


def _scrub_unknown_person_names(ds: Dataset, keep: TagSet) -> list[str]:
    """Blank any Person Name (VR 'PN') element not already handled by the known
    tag table. A PN value is essentially always a person and therefore PHI
    (HIPAA identifier A); a deny-by-default sweep over the VR catches names the
    enumerated table does not list — the commonest residual identifier.
    """
    touched: list[str] = []
    for elem in ds:
        if elem.VR != "PN":
            continue
        pair = (elem.tag.group, elem.tag.element)
        if pair in keep or pair in PHI_TAGS:
            continue
        if elem.value in (None, ""):
            continue
        elem.value = ""
        touched.append(_format_touch(pair, "Z(PN-sweep)"))
    return touched


def _recurse_into_sequences(
    ds: Dataset,
    keep: TagSet,
    mapper: UIDMapper,
    registry: ActionRegistry,
    *,
    keep_private: bool = False,
) -> list[str]:
    touched: list[str] = []
    for elem in ds:
        if elem.VR != "SQ" or not elem.value:
            continue
        for item in elem.value:
            touched.extend(
                _scrub_dataset(item, mapper, keep, registry, keep_private=keep_private)
            )
    return touched


def _scrub_dataset(
    ds: Dataset,
    mapper: UIDMapper,
    keep_tags: TagSet,
    registry: ActionRegistry = DEFAULT_REGISTRY,
    *,
    keep_private: bool = False,
) -> list[str]:
    """Apply known PHI_TAGS actions, sweep private + unknown person-names, and
    recurse into nested Sequence items. Deny-by-default: anything private or any
    PN VR is removed/blanked unless explicitly kept."""
    touched = _apply_point_actions(ds, keep_tags, mapper, registry)
    touched.extend(_scrub_curve_overlay_ranges(ds, keep_tags))
    if not keep_private:
        touched.extend(_strip_private_elements(ds, keep_tags))
    touched.extend(_scrub_unknown_person_names(ds, keep_tags))
    touched.extend(
        _recurse_into_sequences(ds, keep_tags, mapper, registry, keep_private=keep_private)
    )
    return touched


def _format_touch(tag: tuple[int, int], action: str) -> str:
    return f"{tag[0]:04X},{tag[1]:04X}:{action}"


_FILE_META_PHI: frozenset[int] = frozenset({
    0x00020016,  # Source Application Entity Title
    0x00020017,  # Sending Application Entity Title
    0x00020018,  # Receiving Application Entity Title
    0x00020026,  # Source Presentation Address
    0x00020027,  # Sending Presentation Address
    0x00020028,  # Receiving Presentation Address
    0x00020100,  # Private Information Creator UID
    0x00020102,  # Private Information
})


def _scrub_file_meta(ds: Dataset) -> list[str]:
    """Scrub identifying File Meta (group 0002) elements — the AE Titles and
    presentation addresses encode the origin hospital/department and fingerprint
    the source site (a HIPAA geographic identifier). Media Storage SOP Instance
    UID is handled separately (kept consistent with the remapped SOPInstanceUID).
    """
    fm = getattr(ds, "file_meta", None)
    if fm is None:
        return []
    touched: list[str] = []
    for tag_int in _FILE_META_PHI:
        if tag_int in fm:
            del fm[tag_int]
            touched.append(_format_touch((tag_int >> 16, tag_int & 0xFFFF), "X(file_meta)"))
    return touched


def _maintain_file_meta_consistency(
    ds: Dataset,
    original_sop: str | None,
    mapper: UIDMapper,
) -> None:
    """Keep MediaStorageSOPInstanceUID synchronised with SOPInstanceUID."""
    if not original_sop:
        return
    if not (getattr(ds, "file_meta", None) and hasattr(ds.file_meta, "MediaStorageSOPInstanceUID")):
        return
    from pydicom.uid import UID

    new_sop = mapper.remap(original_sop)
    ds.file_meta.MediaStorageSOPInstanceUID = UID(new_sop)


def anonymize_file(
    src: Path,
    dst: Path,
    mapper: UIDMapper,
    *,
    dry_run: bool = False,
    keep_tags: TagSet | None = None,
    registry: ActionRegistry = DEFAULT_REGISTRY,
    keep_private: bool = False,
) -> AuditRecord:
    """Anonymize a single DICOM file and return its audit record."""
    keep = keep_tags if keep_tags is not None else frozenset()
    ds = dcmread(src)
    original_sop = str(ds.SOPInstanceUID) if hasattr(ds, "SOPInstanceUID") else None

    touched = _scrub_dataset(ds, mapper, keep, registry, keep_private=keep_private)
    _maintain_file_meta_consistency(ds, original_sop, mapper)
    touched.extend(_scrub_file_meta(ds))

    output_path: str | None
    if dry_run:
        output_path = None
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        ds.save_as(dst, enforce_file_format=True)
        output_path = str(dst)

    return AuditRecord(
        source=str(src),
        source_sha256=_sha256_file(src),
        output=output_path,
        tags_modified=touched,
        burned_in_phi_warning=_has_burned_in_phi(ds),
        dry_run=dry_run,
        timestamp_utc=utc_now_iso(),
    )


def _resolve_targets(src: Path) -> tuple[list[Path], Path]:
    if src.is_file():
        return ([src], src.parent)
    return (sorted(src.rglob("*.dcm")), src)


def anonymize_path(
    src: Path,
    dst: Path,
    salt: str | None = None,
    *,
    dry_run: bool = False,
    continue_on_error: bool = False,
    keep_tags: TagSet | None = None,
    keep_private: bool = False,
    progress_cb: ProgressCallback | None = None,
    config: AnonymizationConfig | None = None,
) -> AuditSummary:
    """Anonymize a file or directory; return a typed :class:`AuditSummary`.

    Either pass individual options or a fully-built :class:`AnonymizationConfig`
    via *config* (other kwargs are ignored when *config* is supplied).
    """
    cfg = config or AnonymizationConfig(
        salt=salt,
        dry_run=dry_run,
        continue_on_error=continue_on_error,
        keep_tags=keep_tags or frozenset(),
        keep_private=keep_private,
        progress_cb=progress_cb,
    )

    mapper = UIDMapper(salt=cfg.salt)
    targets, base = _resolve_targets(src)
    records: list[AuditRecord] = []
    errors: list[ProcessingError] = []

    for index, target in enumerate(targets, start=1):
        try:
            records.append(anonymize_file(
                target,
                dst / target.relative_to(base),
                mapper,
                dry_run=cfg.dry_run,
                keep_tags=cfg.keep_tags,
                registry=cfg.registry,
                keep_private=cfg.keep_private,
            ))
        except Exception as exc:
            err = ProcessingError(
                source=str(target),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            LOG.warning(
                "anonymize_failed file=%s error=%s: %s",
                target, err.error_type, err.error_message,
            )
            errors.append(err)
            if not cfg.continue_on_error:
                raise
        finally:
            if cfg.progress_cb is not None:
                cfg.progress_cb(index, len(targets), target)

    from dcm_anon import (
        __version__,  # late import avoids circular; __version__ lives in the package init
    )

    return AuditSummary(
        version=__version__ if isinstance(__version__, str) else "0.0.0",
        files_processed=len(records),
        files_failed=len(errors),
        burned_in_warnings=sum(1 for r in records if r.burned_in_phi_warning),
        uid_remapping_count=mapper.size(),
        dry_run=cfg.dry_run,
        records=records,
        errors=errors,
        audit_sha256=audit_sha256(records),
    )


# Re-export for convenience so callers can `from pipeline import Action`.
__all__ = [
    "Action",
    "AnonymizationConfig",
    "AuditRecord",
    "AuditSummary",
    "ProcessingError",
    "ProgressCallback",
    "TagSet",
    "anonymize_file",
    "anonymize_path",
    "parse_keep_tag",
]
