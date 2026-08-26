from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.core.repository_context import (
    RepositoryContextRoots,
    build_repo_context_capabilities,
    discover_agent_files,
    discover_instruction_files,
    discover_skill_roots,
    find_repository_root,
    repository_agents_reminder_hook,
    resolve_repository_context,
)
from suzent.skills.manager import SkillManager


def _write_skill(root: Path, folder: str, name: str, body: str) -> None:
    directory = root / folder
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} description\n---\n{body}\n",
        encoding="utf-8",
    )


def test_discovers_working_and_repository_assets_with_stable_scopes(tmp_path: Path):
    project_dir = tmp_path / "suzent-project"
    repository = tmp_path / "checkout"
    working_dir = repository / "packages" / "api"
    project_dir.mkdir()
    working_dir.mkdir(parents=True)
    (repository / ".git").mkdir()

    _write_skill(working_dir / "skills", "shared", "shared", "working body")
    _write_skill(repository / ".agents" / "skills", "shared", "shared", "repo body")
    agent_file = repository / ".agents" / "agents" / "reviewer.md"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("# Reviewer\n", encoding="utf-8")

    roots = RepositoryContextRoots(
        project_dir=project_dir,
        working_dir=working_dir,
        repository_root=find_repository_root(working_dir),
        home_dir=None,
    )
    discovered_roots = discover_skill_roots(roots)
    discovered_agents = discover_agent_files(roots)

    assert [root.source for root in discovered_roots] == ["repository", "working"]
    assert all(root.virtual_root is None for root in discovered_roots)
    assert [agent.path for agent in discovered_agents] == [agent_file.resolve()]

    manager = SkillManager(
        skills_dir=tmp_path / "empty-global", discovered_roots=discovered_roots
    )
    manager.enabled_skills.clear()
    manager.disabled_skills.clear()
    skills = manager.loader.list_skills()

    assert len(skills) == 2
    assert len({skill.id for skill in skills}) == 2
    assert all(manager.is_skill_enabled(skill.id) for skill in skills)
    assert manager.loader.get_skill("shared").body == "working body"


def test_project_memory_directory_is_not_scanned_for_agent_assets(tmp_path: Path):
    project_dir = tmp_path / "suzent-project"
    working_dir = tmp_path / "working"
    project_dir.mkdir()
    working_dir.mkdir()
    _write_skill(project_dir / "skills", "memory-skill", "memory-skill", "body")

    roots = RepositoryContextRoots(project_dir, working_dir, None, home_dir=None)

    assert roots.unique_asset_bases() == (("working", working_dir.resolve()),)
    assert discover_skill_roots(roots) == []


def test_discovers_user_level_assistant_skills(tmp_path: Path):
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "suzent-project"
    working_dir = tmp_path / "working"
    project_dir.mkdir()
    working_dir.mkdir()
    _write_skill(home_dir / ".claude" / "skills", "personal", "personal", "body")

    roots = RepositoryContextRoots(
        project_dir,
        working_dir,
        None,
        home_dir=home_dir,
    )
    discovered = discover_skill_roots(roots)

    assert [(root.source, root.path) for root in discovered] == [
        ("home", (home_dir / ".claude" / "skills").resolve())
    ]


def test_discovers_namespaced_codex_system_skills(tmp_path: Path):
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "suzent-project"
    working_dir = tmp_path / "working"
    project_dir.mkdir()
    working_dir.mkdir()
    system_root = home_dir / ".codex" / "skills" / ".system"
    _write_skill(system_root, "skill-creator", "skill-creator", "body")

    roots = RepositoryContextRoots(
        project_dir,
        working_dir,
        None,
        home_dir=home_dir,
    )
    discovered = discover_skill_roots(roots)

    assert [(root.source, root.path) for root in discovered] == [
        ("home", system_root.resolve())
    ]


def test_canonical_source_is_not_loaded_again_as_repository_skill(tmp_path: Path):
    canonical = tmp_path / "skills"
    _write_skill(canonical, "shared", "shared", "same body")
    discovered = [
        SimpleNamespace(
            path=canonical,
            source="repository",
            source_id="repository:test:skills",
            virtual_root=None,
            default_enabled=True,
        )
    ]

    manager = SkillManager(skills_dir=canonical, discovered_roots=discovered)

    assert len(manager.loader.list_skills()) == 1
    assert manager.loader.list_skills()[0].path == canonical / "shared" / "SKILL.md"


def test_existing_repository_mount_is_reused_for_skill_paths(tmp_path: Path):
    repository = tmp_path / "repo"
    canonical = repository / "skills"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_skill(canonical, "shared", "shared", "body")

    manager = SkillManager(
        skills_dir=canonical,
        existing_volumes=[f"{repository}:/mnt/repository"],
        project_dir=project_dir,
    )

    assert manager.required_mounts == []
    assert manager.loader.list_skills()[0].virtual_path == (
        "/mnt/repository/skills/shared/SKILL.md"
    )


def test_uncovered_canonical_skill_source_is_mounted_read_only(tmp_path: Path):
    canonical = tmp_path / "skills"
    project_dir = tmp_path / "project"
    empty_global = tmp_path / "empty-global"
    project_dir.mkdir()
    _write_skill(canonical, "shared", "shared", "body")

    manager = SkillManager(
        skills_dir=empty_global,
        discovered_roots=[
            SimpleNamespace(
                path=canonical,
                source="repository",
                source_id="repository:test:skills",
                virtual_root=None,
                default_enabled=True,
            )
        ],
        project_dir=project_dir,
    )

    assert manager.required_mounts == [
        f"{canonical.resolve()}:/mnt/skills/discovered/repository-test-skills:ro"
    ]


def test_chat_repository_context_comes_from_its_volume_not_process_cwd(
    tmp_path: Path, monkeypatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / ".git").mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    chat = SimpleNamespace(
        working_directory=None,
        config={"sandbox_volumes": [f"{repository}:/mnt/repository"]},
    )
    database = SimpleNamespace(
        get_project_dir=lambda _chat_id: project_dir,
        get_chat=lambda _chat_id: chat,
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: database)

    roots = resolve_repository_context("chat")

    assert roots.working_dir == repository.resolve()
    assert roots.repository_root == repository.resolve()


def test_chat_skill_manager_reuses_persisted_repository_mount(
    tmp_path: Path, monkeypatch
):
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    _write_skill(repository / ".codex" / "skills", "local", "local", "body")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    chat = SimpleNamespace(
        working_directory=None,
        config={"sandbox_volumes": [f"{repository}:/mnt/repository"]},
    )
    database = SimpleNamespace(
        get_project_dir=lambda _chat_id: project_dir,
        get_chat=lambda _chat_id: chat,
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: database)
    monkeypatch.setattr("suzent.config.model.CONFIG.sandbox_volumes", [])

    from suzent.skills.manager import get_skill_manager_for_chat

    manager = get_skill_manager_for_chat("chat")
    skill = next(
        skill
        for skill in manager.loader.list_skills()
        if skill.metadata.name == "local"
    )

    assert skill.virtual_path == "/mnt/repository/.codex/skills/local/SKILL.md"
    assert all(str(repository) not in volume for volume in manager.required_mounts)


def test_context_roots_deduplicate_project_that_is_also_repository(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    roots = RepositoryContextRoots(tmp_path, tmp_path, tmp_path, home_dir=None)

    assert roots.unique_asset_bases() == (("repository", tmp_path.resolve()),)
    capabilities = build_repo_context_capabilities(roots)
    assert len(capabilities) == 1
    assert capabilities[0].home_dir == tmp_path.resolve()


def test_discovers_walk_up_instruction_files_ancestor_first(tmp_path: Path):
    repository = tmp_path / "repository"
    working = repository / "packages" / "api"
    working.mkdir(parents=True)
    (repository / ".git").mkdir()
    root_agents = repository / "AGENTS.md"
    package_claude = repository / "packages" / "CLAUDE.md"
    working_agents = working / "AGENTS.md"
    root_agents.write_text("root", encoding="utf-8")
    package_claude.write_text("package", encoding="utf-8")
    working_agents.write_text("working", encoding="utf-8")
    roots = RepositoryContextRoots(
        tmp_path / "project",
        working,
        repository,
        home_dir=None,
    )

    discovered = discover_instruction_files(roots)

    assert [item.path for item in discovered] == [
        root_agents.resolve(),
        package_claude.resolve(),
        working_agents.resolve(),
    ]
    assert [item.source for item in discovered] == [
        "repository",
        "repository",
        "working",
    ]


def test_instruction_discovery_deduplicates_identical_content(tmp_path: Path):
    repository = tmp_path / "repository"
    working = repository / "package"
    working.mkdir(parents=True)
    (repository / ".git").mkdir()
    (repository / "AGENTS.md").write_text("same", encoding="utf-8")
    (working / "CLAUDE.md").write_text("same", encoding="utf-8")
    roots = RepositoryContextRoots(
        tmp_path / "project",
        working,
        repository,
        home_dir=None,
    )

    discovered = discover_instruction_files(roots)

    assert [item.path for item in discovered] == [(repository / "AGENTS.md").resolve()]


@pytest.mark.asyncio
async def test_repository_agent_files_are_surfaced_with_workspace_paths(tmp_path: Path):
    agent_file = tmp_path / ".agents" / "agents" / "reviewer.md"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("# Reviewer\n", encoding="utf-8")
    roots = RepositoryContextRoots(tmp_path, tmp_path, tmp_path, home_dir=None)
    deps = SimpleNamespace(
        repository_agent_files=discover_agent_files(roots),
        sandbox_enabled=True,
        path_resolver=SimpleNamespace(
            to_virtual_path=lambda path: (
                f"/workspace/{path.relative_to(tmp_path).as_posix()}"
            )
        ),
    )

    reminder = await repository_agents_reminder_hook("chat", deps)

    assert reminder is not None
    assert "reviewer (repository)" in reminder
    assert "/workspace/.agents/agents/reviewer.md" in reminder


@pytest.mark.asyncio
async def test_repository_agent_files_use_custom_mount_paths(tmp_path: Path):
    project_dir = tmp_path / "project"
    repository = tmp_path / "repository"
    project_dir.mkdir()
    agent_file = repository / ".agents" / "agents" / "reviewer.md"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("# Reviewer\n", encoding="utf-8")
    roots = RepositoryContextRoots(
        project_dir,
        repository,
        repository,
        home_dir=None,
    )
    from suzent.tools.filesystem.path_resolver import PathResolver

    deps = SimpleNamespace(
        repository_agent_files=discover_agent_files(roots),
        sandbox_enabled=True,
        path_resolver=PathResolver(
            "chat",
            True,
            project_slug="project",
            sandbox_data_path=tmp_path / "sandbox",
            custom_volumes=[f"{repository}:/mnt/repository"],
        ),
    )

    reminder = await repository_agents_reminder_hook("chat", deps)

    assert reminder is not None
    assert "/mnt/repository/.agents/agents/reviewer.md" in reminder
    assert str(repository) not in reminder
