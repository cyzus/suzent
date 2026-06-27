"""Tests for PathResolver.find_files directory pruning.

find_files used to materialize every path under the search root via
``Path.glob("**/*")`` (descending into .git/node_modules/.venv/target) and call
``.resolve()`` per file, which timed out grep/glob on large repos. The walk now
prunes heavy directories unless explicitly targeted.
"""

from suzent.tools.filesystem.path_resolver import DEFAULT_PRUNED_DIRS, PathResolver


def _make_resolver(tmp_path):
    return PathResolver(
        chat_id="test-chat",
        sandbox_enabled=False,
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
    )


def _build_tree(workspace):
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "main.py").write_text("print('hi')\n")
    (workspace / "README.md").write_text("# readme\n")

    # Heavy dirs that should be pruned from recursive walks.
    for pruned in ("node_modules", ".git", ".venv", "target"):
        d = workspace / pruned / "deep"
        d.mkdir(parents=True)
        (d / "junk.py").write_text("x = 1\n")


def test_find_files_prunes_heavy_directories(tmp_path):
    workspace = tmp_path / "workspace"
    _build_tree(workspace)
    resolver = _make_resolver(tmp_path)

    found = resolver.find_files("**/*.py", str(workspace))
    vpaths = {v for _, v in found}

    # Real source is found...
    assert any(v.endswith("src/main.py") for v in vpaths)
    # ...but nothing inside a pruned directory leaks in.
    assert not any(
        any(part in DEFAULT_PRUNED_DIRS for part in v.split("/")) for v in vpaths
    )


def test_find_files_descends_into_pruned_dir_when_explicitly_targeted(tmp_path):
    workspace = tmp_path / "workspace"
    _build_tree(workspace)
    resolver = _make_resolver(tmp_path)

    # Explicitly targeting node_modules should still search inside it.
    found = resolver.find_files("**/*.py", str(workspace / "node_modules"))
    vpaths = [v for _, v in found]

    assert any(v.endswith("junk.py") for v in vpaths)


def test_find_files_non_recursive_pattern_still_works(tmp_path):
    workspace = tmp_path / "workspace"
    _build_tree(workspace)
    resolver = _make_resolver(tmp_path)

    found = resolver.find_files("*.md", str(workspace))
    vpaths = [v for _, v in found]

    assert any(v.endswith("README.md") for v in vpaths)
    assert not any(v.endswith("main.py") for v in vpaths)
