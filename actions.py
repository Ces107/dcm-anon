"""PS3.15 anonymization actions.

Each action is a small, named operation that mutates a DICOM dataset for one
specific tag. The :class:`Action` enum replaces the historical "X"/"Z"/"U"/"D"
magic strings used in older de-id tools, and the :class:`ActionRegistry` exposes
an open dispatch surface so new actions can be plugged in without touching
:mod:`pipeline`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from pydicom.dataset import Dataset

    from uid_mapper import UIDMapper


class Action(str, Enum):
    """PS3.15 Table E.1-1 action code.

    Inherits from :class:`str` so the value round-trips cleanly through JSON
    audit logs without custom encoders.
    """

    X = "X"  # remove element
    Z = "Z"  # replace with VR-appropriate placeholder
    U = "U"  # remap UID consistently
    D = "D"  # standard says non-zero dummy; we treat as remove

    @classmethod
    def all_codes(cls) -> frozenset[str]:
        return frozenset(member.value for member in cls)


# ---------------------------------------------------------------------------
# Action handlers — pure-ish functions taking (dataset, tag, mapper).
# Importing pydicom and the placeholder table here keeps the call sites in
# pipeline.py free of those concerns.
# ---------------------------------------------------------------------------

ActionFn = Callable[["Dataset", tuple[int, int], "UIDMapper"], None]


def _strip(ds: Dataset, tag: tuple[int, int], _: UIDMapper) -> None:
    if tag in ds:
        del ds[tag]


def _replace(ds: Dataset, tag: tuple[int, int], _: UIDMapper) -> None:
    if tag not in ds:
        return
    from phi_table import PLACEHOLDERS

    ds[tag].value = PLACEHOLDERS.get(tag, "")


def _remap(ds: Dataset, tag: tuple[int, int], mapper: UIDMapper) -> None:
    if tag not in ds:
        return
    original = str(ds[tag].value)
    if original:
        ds[tag].value = mapper.remap(original)


@dataclass(frozen=True)
class ActionRegistry:
    """Open dispatch table mapping Action → handler.

    Closed by default but can be extended (Open/Closed Principle) by composing
    a new registry with :meth:`with_override`.
    """

    handlers: dict[Action, ActionFn]

    def apply(
        self,
        action: Action,
        ds: Dataset,
        tag: tuple[int, int],
        mapper: UIDMapper,
    ) -> None:
        self.handlers[action](ds, tag, mapper)

    def with_override(self, action: Action, fn: ActionFn) -> ActionRegistry:
        return ActionRegistry({**self.handlers, action: fn})


DEFAULT_REGISTRY: ActionRegistry = ActionRegistry({
    Action.X: _strip,
    Action.Z: _replace,
    Action.U: _remap,
    Action.D: _strip,  # conformant: remove is at least as strong as dummy
})
