"""Single source of truth for the package version.

A standalone module holding only a literal assignment so setuptools can read it
statically (pyproject ``[tool.setuptools.dynamic]``) without importing the whole
package, and so the runtime ``__version__`` never drifts from the built dist —
the previous ``importlib.metadata.version`` approach went stale under editable
installs and silently mislabelled which code produced a compliance manifest.
"""

__version__ = "0.6.0"
