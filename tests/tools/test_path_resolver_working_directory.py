"""A chat's authorized working directory must reach every file tool.

The shell tool has always executed in ``deps.cwd``; the path resolver did not
know about it, so the same folder was writable from bash and rejected by read,
edit, glob and grep.
"""

import pytest

from suzent.tools.filesystem.path_resolver import PathResolver


@pytest.fixture
def target_folder(tmp_path):
    folder = tmp_path / "Documents" / "project" / "assets"
    (folder / "captions").mkdir(parents=True)
    (folder / "notes.txt").write_text("top level")
    (folder / "captions" / "a.txt").write_text("nested")
    return folder


def make_resolver(tmp_path, cwd=None, custom_volumes=None):
    return PathResolver(
        chat_id="test-chat",
        sandbox_enabled=False,
        project_slug="default",
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
        custom_volumes=custom_volumes,
        cwd=str(cwd) if cwd else None,
    )


def test_working_directory_is_the_agent_cwd(tmp_path, target_folder):
    resolver = make_resolver(tmp_path, cwd=target_folder)

    assert resolver.get_working_dir() == target_folder.resolve()


def test_project_dir_remains_the_cwd_when_no_folder_is_authorized(tmp_path):
    resolver = make_resolver(tmp_path)

    assert resolver.get_working_dir() == resolver.project_dir


def test_absolute_paths_inside_the_working_directory_resolve(tmp_path, target_folder):
    resolver = make_resolver(tmp_path, cwd=target_folder)

    assert resolver.resolve(str(target_folder)) == target_folder.resolve()
    assert (
        resolver.resolve(str(target_folder / "captions" / "a.txt"))
        == (target_folder / "captions" / "a.txt").resolve()
    )


def test_relative_paths_resolve_against_the_working_directory(tmp_path, target_folder):
    resolver = make_resolver(tmp_path, cwd=target_folder)

    assert resolver.resolve("notes.txt") == (target_folder / "notes.txt").resolve()


def test_glob_enumerates_the_working_directory_without_an_explicit_root(
    tmp_path, target_folder
):
    resolver = make_resolver(tmp_path, cwd=target_folder)

    found = {host for host, _virtual in resolver.find_files("**/*.txt", None)}

    assert found == {
        (target_folder / "notes.txt").resolve(),
        (target_folder / "captions" / "a.txt").resolve(),
    }


def test_glob_enumerates_the_working_directory_by_absolute_root(
    tmp_path, target_folder
):
    resolver = make_resolver(tmp_path, cwd=target_folder)

    found = {
        host for host, _virtual in resolver.find_files("**/*.txt", str(target_folder))
    }

    assert len(found) == 2


def test_rootless_glob_falls_back_to_the_project_dir_in_host_mode(tmp_path):
    # Previously this resolved "/" and was denied outright, so a bare
    # glob_search("**/*.py") failed on the host with an outside-workspace error.
    resolver = make_resolver(tmp_path)
    (resolver.project_dir / "module.py").write_text("x = 1")

    found = [host for host, _virtual in resolver.find_files("**/*.py", None)]

    assert found == [(resolver.project_dir / "module.py").resolve()]


def test_host_mode_reports_paths_outside_the_grants_without_refusing_them(
    tmp_path, target_folder
):
    # On the host the grant list is advisory: it covers the file tools and a
    # handful of shell commands, so refusing here only blocked the reviewable,
    # approval-gated tools while every interpreter went through. Callers ask allows()
    # and route the operation to approval instead.
    resolver = make_resolver(tmp_path, cwd=target_folder)
    sibling = target_folder.parent / "secrets.txt"
    sibling.write_text("nope")

    resolved = resolver.resolve(str(sibling))

    assert resolved == sibling.resolve()
    assert resolver.allows(resolved) is False
    assert resolver.allows(target_folder / "notes.txt") is True


def test_sandbox_mode_still_refuses_paths_outside_every_grant(tmp_path, target_folder):
    resolver = PathResolver(
        chat_id="test-chat",
        sandbox_enabled=True,
        project_slug="default",
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
        cwd=str(target_folder),
    )

    with pytest.raises(ValueError):
        resolver.resolve("/mnt/not-registered/file.txt")


def test_denial_names_every_grant_and_a_recovery_action(tmp_path, target_folder):
    resolver = PathResolver(
        chat_id="test-chat",
        sandbox_enabled=True,
        project_slug="default",
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
        custom_volumes=[f"{tmp_path / 'shared-notes'}:/mnt/notes"],
        cwd=str(target_folder),
    )

    with pytest.raises(ValueError) as excinfo:
        resolver._validate_within_workspace(tmp_path / "elsewhere" / "file.txt")

    message = str(excinfo.value)
    assert str(target_folder.resolve()) in message
    assert "/mnt/notes" in message
    assert "custom volume" in message


def test_granted_roots_are_shared_by_both_validators(tmp_path, target_folder):
    resolver = make_resolver(tmp_path, cwd=target_folder)
    labels = {label for label, _path in resolver.granted_roots()}

    assert "working directory" in labels
    # The workspace root is only a grant for absolute host paths, so it is opt-in.
    assert "workspace" not in labels
    assert "workspace" in {
        label for label, _path in resolver.granted_roots(include_workspace=True)
    }


def test_sandbox_mode_reaches_granted_directories_by_host_path(tmp_path, target_folder):
    # Sandbox mode maps virtual roots, but a granted directory must resolve the
    # same way whichever address is used. Previously an absolute host path was
    # silently rewritten to project_dir/<the whole path> — a different file, and
    # no error, because the rewritten path passed validation.
    resolver = PathResolver(
        chat_id="test-chat",
        sandbox_enabled=True,
        project_slug="default",
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
        custom_volumes=[f"{target_folder}:/mnt/assets"],
        cwd=str(target_folder),
    )

    expected = (target_folder / "notes.txt").resolve()
    assert resolver.resolve("notes.txt") == expected
    assert resolver.resolve(str(target_folder / "notes.txt")) == expected
    assert resolver.resolve("/mnt/assets/notes.txt") == expected


def test_sandbox_mode_still_maps_ungranted_absolute_paths_virtually(tmp_path):
    # Nothing new becomes reachable: an ungranted host path keeps falling
    # through to the virtual mapping instead of escaping the sandbox roots.
    resolver = PathResolver(
        chat_id="test-chat",
        sandbox_enabled=True,
        project_slug="default",
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
    )

    resolved = resolver.resolve("/etc/passwd")

    assert resolved == (resolver.project_dir / "etc" / "passwd").resolve()
    assert resolver.allows(resolved)
