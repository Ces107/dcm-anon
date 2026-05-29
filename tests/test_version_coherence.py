"""Version coherence: the single source of truth must match every surface a
procurement reviewer inspects (CHANGELOG latest heading, landing page).

A compliance tool's provenance is the product; four different version strings
across artifacts reads as an unmaintained project. These tests fail the build
on drift so the version is bumped in exactly one place (dcm_anon/_version.py).
"""
from __future__ import annotations

import re
from pathlib import Path

from dcm_anon._version import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_changelog_latest_versioned_heading_matches() -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    assert match is not None, "no versioned '## [X.Y.Z]' heading in CHANGELOG.md"
    assert match.group(1) == __version__, (
        f"CHANGELOG latest {match.group(1)!r} != _version {__version__!r}"
    )


def test_landing_page_shows_current_version() -> None:
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert f"v{__version__}" in html, (
        f"docs/index.html does not mention v{__version__}"
    )
    # And must not still advertise a stale prior minor.
    assert "v0.4.0" not in html and "v0.5.0" not in html
