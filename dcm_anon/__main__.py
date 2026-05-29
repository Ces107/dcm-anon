"""Enable ``python -m dcm_anon``.

A reflexive ``python -m dcm_anon ...`` (common in sandboxed/CI environments
where the console script is not on PATH) must run the CLI, not silently exit 0.
"""
from __future__ import annotations

from dcm_anon.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
