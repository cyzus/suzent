import subprocess
from pathlib import Path

import pytest

from suzent.sync.github_token import git_push_with_token


def test_git_push_with_token_redacts_token_in_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr=(
                "To https://x-access-token:TOKEN_VALUE@github.com/alice/brain.git\n"
                "! [rejected] main -> main"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        git_push_with_token(
            tmp_path,
            "https://x-access-token:TOKEN_VALUE@github.com/alice/brain.git",
            "main",
        )

    message = str(exc_info.value)
    assert "TOKEN_VALUE" not in message
    assert "https://<redacted>@github.com/alice/brain.git" in message
