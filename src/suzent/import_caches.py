"""Let imports see packages installed while the server runs."""

from __future__ import annotations

import importlib.machinery
import os
import sys
import zipimport


def refresh_import_caches() -> None:
    """Forget cached directory listings so newly installed packages import.

    Does what ``importlib.invalidate_caches()`` does, except for zipimport:
    there it re-reads the whole directory of the desktop runtime's
    pure-packages.zip (tens of thousands of entries, seconds on a cold disk),
    and nothing is ever installed into that zip.
    """
    for name, finder in list(sys.path_importer_cache.items()):
        if finder is None or not os.path.isabs(name):
            # A path that had no finder (e.g. a plugin dir not created yet).
            del sys.path_importer_cache[name]
        elif isinstance(finder, zipimport.zipimporter):
            continue
        elif hasattr(finder, "invalidate_caches"):
            finder.invalidate_caches()
    for finder in sys.meta_path:
        if finder is not importlib.machinery.PathFinder and hasattr(
            finder, "invalidate_caches"
        ):
            finder.invalidate_caches()
    # Namespace packages recompute their __path__ when this changes.
    from importlib import _bootstrap_external

    _bootstrap_external._NamespacePath._epoch += 1
