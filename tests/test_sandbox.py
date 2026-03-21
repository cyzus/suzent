"""Deprecated legacy sandbox test module.

The old microsandbox/Firecracker integration suite was retired after migrating
to the Docker-based sandbox runtime. This module is intentionally skipped.
"""

import pytest

pytest.skip(
    "Deprecated: legacy sandbox tests were removed after Docker sandbox migration.",
    allow_module_level=True,
)
