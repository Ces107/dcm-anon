"""PS3.15 anonymization actions: Action enum and handler dispatch table."""
from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING

from pydicom.multival import MultiValue

if TYPE_CHECKING:  # pragma: no cover
    from pydicom.dataset import Dataset

    from dcm_anon.uid_mapper import UIDMapper


# PS3.15 E.1-1 action codes. str mixin = free JSON round-trip.
class Action(str, Enum):
    X = "X"  # remove element
    Z = "Z"  # replace with VR-appropriate placeholder
    U = "U"  # remap UID consistently
    D = "D"  # standard says non-zero dummy; we treat as remove


# Action handlers — pure-ish functions taking (dataset, tag, mapper).
# Importing pydicom and the placeholder table here keeps the call sites in
# pipeline.py free of those concerns.

ActionFn = Callable[["Dataset", tuple[int, int], "UIDMapper"], None]


def _strip(ds: Dataset, tag: tuple[int, int], _: UIDMapper) -> None:
    if tag in ds:
        del ds[tag]


def _replace(ds: Dataset, tag: tuple[int, int], _: UIDMapper) -> None:
    if tag not in ds:
        return
    from dcm_anon.phi_table import PLACEHOLDERS

    ds[tag].value = PLACEHOLDERS.get(tag, "")


def _remap(ds: Dataset, tag: tuple[int, int], mapper: UIDMapper) -> None:
    if tag not in ds:
        return
    element = ds[tag]
    value = element.value
    if isinstance(value, (MultiValue, list, tuple)):
        # Multi-valued UID element (e.g. ReferencedSOPInstanceUID in RT-STRUCT /
        # KOS / presentation states). Remap each member independently — str() over
        # the whole MultiValue would collapse N UIDs into ONE bracketed-repr hash,
        # silently severing every cross-reference the dataset depends on (CF-08).
        element.value = [mapper.remap(str(v)) for v in value if str(v)]
        return
    original = str(value)
    if original:
        element.value = mapper.remap(original)


ActionRegistry = dict[Action, ActionFn]

DEFAULT_REGISTRY: ActionRegistry = {
    Action.X: _strip,
    Action.Z: _replace,
    Action.U: _remap,
    Action.D: _strip,  # conformant: remove is at least as strong as dummy
}
