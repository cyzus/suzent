from pathlib import Path
from unittest.mock import patch

from suzent.sync import quickstart as quickstart_module


def test_resolve_gh_cli_windows_program_files():
    with patch.object(quickstart_module.shutil, "which", return_value=None):
        with patch.object(quickstart_module.sys, "platform", "win32"):
            candidate = Path(r"C:\Program Files\GitHub CLI\gh.exe")
            with patch.object(Path, "is_file", autospec=True) as is_file:
                is_file.side_effect = lambda self: self == candidate
                assert (
                    quickstart_module.resolve_gh_cli()
                    == r"C:\Program Files\GitHub CLI\gh.exe"
                )
