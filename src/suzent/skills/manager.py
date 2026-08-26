from pathlib import Path
import re
from typing import Optional
from suzent.config import (
    OFFICIAL_SKILLS_DIR,
    USER_CONFIG_DIR,
    USER_SKILLS_DIR,
    get_external_skill_sources,
    sync_managed_skills_dirs,
)
from suzent.config.paths import LEGACY_USER_SKILLS_DIR
from suzent.logger import get_logger
from suzent.tools.filesystem.path_resolver import PathResolver
from .loader import SkillLoader

logger = get_logger(__name__)


def _mount_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "skills"


def _virtual_path_under_mount(path: Path, mounts: list[tuple[Path, str]]) -> str | None:
    """Map a host path through the most specific existing sandbox mount."""
    resolved = path.resolve()
    matches: list[tuple[int, str]] = []
    for host_root, virtual_root in mounts:
        try:
            relative = resolved.relative_to(host_root.resolve())
        except ValueError:
            continue
        suffix = relative.as_posix()
        virtual = virtual_root.rstrip("/")
        matches.append(
            (
                len(host_root.resolve().parts),
                virtual if suffix == "." else f"{virtual}/{suffix}",
            )
        )
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


class SkillManager:
    _instance = None

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        *,
        discovered_roots: Optional[list[object]] = None,
        existing_volumes: Optional[list[str]] = None,
        project_dir: Optional[Path] = None,
        sandbox_enabled: bool = True,
    ):
        self.uses_default_sources = skills_dir is None
        self.skills_dirs: list[Path]
        preferred_virtual_roots: dict[Path, str] = {}
        if skills_dir is None:
            sync_managed_skills_dirs()
            external_sources = get_external_skill_sources()
            external_dirs = [source for source, _ in external_sources]
            self.skills_dirs = [OFFICIAL_SKILLS_DIR]
            if LEGACY_USER_SKILLS_DIR.is_dir():
                self.skills_dirs.append(LEGACY_USER_SKILLS_DIR)
            self.skills_dirs.extend([*external_dirs, USER_SKILLS_DIR])
            virtual_roots = {
                OFFICIAL_SKILLS_DIR: "/mnt/skills/official",
                USER_SKILLS_DIR: "/mnt/skills/user",
            }
            source_roots = {
                OFFICIAL_SKILLS_DIR: "official",
                USER_SKILLS_DIR: "user",
            }
            source_ids = {
                OFFICIAL_SKILLS_DIR: "official",
                USER_SKILLS_DIR: "user",
            }
            if LEGACY_USER_SKILLS_DIR.is_dir():
                source_roots[LEGACY_USER_SKILLS_DIR] = "user"
                source_ids[LEGACY_USER_SKILLS_DIR] = "user:legacy"
            for external_dir, (_, identity_path) in zip(
                external_dirs, external_sources, strict=True
            ):
                virtual_roots[external_dir] = (
                    f"/mnt/skills/external/{identity_path.name}"
                )
                source_roots[external_dir] = "external"
                source_ids[external_dir] = f"external:{identity_path.name}"
        else:
            self.skills_dirs = [skills_dir]
            virtual_roots = {}
            source_roots = {}
            source_ids = {}

        default_enabled_roots: set[Path] = set()
        for discovered in discovered_roots or []:
            root = Path(discovered.path)
            if root.resolve() in {path.resolve() for path in self.skills_dirs}:
                continue
            self.skills_dirs.append(root)
            source_roots[root] = discovered.source
            source_ids[root] = discovered.source_id
            if discovered.virtual_root:
                virtual_roots[root] = discovered.virtual_root
            else:
                namespace = _mount_segment(discovered.source_id)
                virtual_roots[root] = f"/mnt/skills/discovered/{namespace}"
            if discovered.default_enabled:
                default_enabled_roots.add(root)

        preferred_virtual_roots.update(virtual_roots)
        mount_mappings: list[tuple[Path, str]] = []
        if project_dir is not None:
            mount_mappings.append((project_dir.resolve(), "/workspace"))
        for volume in existing_volumes or []:
            parsed = PathResolver.parse_volume_string(volume)
            if parsed:
                host, virtual = parsed
                mount_mappings.append((Path(host).resolve(), virtual))

        self.required_mounts: list[str] = []
        if sandbox_enabled:
            # Mount broader roots first so nested legacy/vendor libraries reuse
            # the parent mapping instead of creating overlapping Docker mounts.
            for root in sorted(
                self.skills_dirs, key=lambda path: len(path.resolve().parts)
            ):
                if not root.is_dir():
                    continue
                covered = _virtual_path_under_mount(root, mount_mappings)
                if covered:
                    virtual_roots[root] = covered
                    continue
                preferred = preferred_virtual_roots.get(root)
                if preferred:
                    self.required_mounts.append(f"{root.resolve()}:{preferred}")
                    mount_mappings.append((root.resolve(), preferred))

        self.skills_dir = self.skills_dirs[-1]
        self.loader = SkillLoader(
            self.skills_dirs,
            virtual_roots=virtual_roots,
            source_roots=source_roots,
            source_ids=source_ids,
            default_enabled_roots=default_enabled_roots,
        )
        self.persistence_file = USER_CONFIG_DIR / "skills.json"

        # Initialize enabled state
        self.enabled_skills = set()
        self.disabled_skills = set()
        self._load_enabled_state()

        logger.info(f"SkillManager initialized with directories: {self.skills_dirs}")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SkillManager()
        return cls._instance

    def _load_enabled_state(self):
        """Load enabled skills from persistence file."""
        if self.persistence_file.exists():
            try:
                import json

                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.enabled_skills = set(data.get("enabled", []))
                    self.disabled_skills = set(data.get("disabled", []))
            except Exception as e:
                logger.error(f"Failed to load skills state: {e}")
        else:
            # Default to all enabled if no state exists?
            # Or default to disabled? Protocol says "toggle which skills to be enabled".
            # Let's default to disabled (empty set) to match "only equipped when enabled" philosophy,
            # OR default to all enabled for backward compat?
            # User said "it will only be equipped when there are skills enabled".
            # Let's start with EMPTY (disabled) so user explicitly enables them, as implied by "toggle...enabled".
            pass

    def _save_enabled_state(self):
        """Save enabled skills to persistence file."""
        try:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            import json

            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "enabled": sorted(self.enabled_skills),
                        "disabled": sorted(self.disabled_skills),
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"Failed to save skills state: {e}")

    def is_skill_enabled(self, identifier: str) -> bool:
        skill = self.loader.get_skill(identifier)
        if skill is None:
            return False
        if skill.id in self.disabled_skills:
            return False
        return (
            skill.id in self.enabled_skills
            or skill.metadata.name in self.enabled_skills
            or skill.default_enabled
        )

    def enable_skill(self, identifier: str):
        skill = self.loader.get_skill(identifier)
        key = skill.id if skill else identifier
        self.disabled_skills.discard(key)
        self.enabled_skills.add(key)
        self._save_enabled_state()

    def disable_skill(self, identifier: str):
        skill = self.loader.get_skill(identifier)
        key = skill.id if skill else identifier
        self.enabled_skills.discard(key)
        self.disabled_skills.add(key)
        self._save_enabled_state()

    def toggle_skill(self, identifier: str) -> bool:
        """Toggle skill state and return new state (True=Enabled)."""
        if self.is_skill_enabled(identifier):
            self.disable_skill(identifier)
            return False
        else:
            self.enable_skill(identifier)
            return True

    def reload(self):
        """Reload all skills from disk."""
        if self.uses_default_sources:
            sync_managed_skills_dirs()
        self.loader.load_skills()
        # Re-verify enabled skills exist?
        available_ids = {s.id for s in self.loader.list_skills()}
        available_names = {s.metadata.name for s in self.loader.list_skills()}
        available = available_ids | available_names
        self.enabled_skills.intersection_update(available)
        self.disabled_skills.intersection_update(available_ids)
        self._save_enabled_state()

    def get_skill_descriptions(self) -> str:
        """
        Generate skill descriptions for tool/system prompt (Layer 1).
        """
        skills = self.loader.list_skills()
        if not skills:
            return "(no skills available)"

        return "\n".join(
            f"- {skill.metadata.name}: {skill.metadata.description}"
            for skill in skills
            if self.is_skill_enabled(skill.id)
        )

    def has_enabled_skills(self) -> bool:
        return any(
            self.is_skill_enabled(skill.id) for skill in self.loader.list_skills()
        )

    def get_skills_listing(self, sandbox_enabled: bool = True) -> str:
        """
        Generate a markdown list of available skills for context injection.
        """
        skills = self.loader.list_skills()
        if not skills:
            return "(no skills available)"

        lines = []
        for skill in skills:
            if not self.is_skill_enabled(skill.id):
                continue
            if sandbox_enabled:
                location = skill.virtual_path or PathResolver.get_skill_virtual_path(
                    skill.metadata.name
                )
            else:
                location = str(skill.path.resolve())

            lines.append(
                f"- {skill.metadata.name}: {skill.metadata.description} (Location: {location})"
            )

        if not lines:
            return "(no enabled skills available)"

        return "\n".join(lines)

    def get_skill_content(
        self, identifier: str, sandbox_enabled: bool = True
    ) -> Optional[str]:
        """
        Get full skill content for injection (Layer 2 + 3).
        """
        skill = self.loader.get_skill(identifier)
        if not skill:
            return None

        content = f"# Skill: {skill.metadata.name}\n\n{skill.body}"
        if not sandbox_enabled:
            if skill.virtual_path:
                virtual_dir = skill.virtual_path.rsplit("/", 1)[0]
                content = content.replace(virtual_dir, str(skill.dir))
            content = self._adapt_skill_content_for_host(content)

        # List available resources (Layer 3 hints)
        resources = []
        for folder, label in [
            ("scripts", "Scripts"),
            ("references", "References"),
            ("assets", "Assets"),
        ]:
            folder_path = skill.dir / folder
            if folder_path.exists():
                files = list(folder_path.glob("*"))
                if files:
                    file_list = ", ".join(f.name for f in files)
                    resources.append(f"{label}: {file_list}")

        if resources:
            resource_dir = (
                skill.virtual_path.rsplit("/", 1)[0]
                if sandbox_enabled and skill.virtual_path
                else str(skill.dir)
            )
            content += f"\n\n**Available resources in {resource_dir}:**\n"
            content += "\n".join(f"- {r}" for r in resources)

        return content

    @staticmethod
    def _adapt_skill_content_for_host(content: str) -> str:
        """Rewrite sandbox-only path literals to host-friendly env var paths."""
        replacements = [
            ("/mnt/notebook", "${MOUNT_NOTEBOOK}"),
            ("/shared/memory", "${SHARED_PATH}/memory"),
            ("/shared", "${SHARED_PATH}"),
            ("/workspace", "${PROJECT_PATH}"),
            # /persistence is a legacy virtual alias for the per-chat project dir
            # (PathResolver maps it to project_dir). On the host it maps to PROJECT_PATH;
            # there is no PERSISTENCE_PATH env var.
            ("/persistence", "${PROJECT_PATH}"),
        ]

        adapted = content
        for old, new in replacements:
            adapted = adapted.replace(old, new)
        return adapted


def get_skill_manager():
    return SkillManager.get_instance()


def get_skill_manager_for_chat(
    chat_id: str | None,
    cwd: str | None = None,
    *,
    custom_volumes: list[str] | None = None,
    sandbox_enabled: bool = True,
) -> SkillManager:
    """Return a manager layered with skills discovered for the active context."""
    from suzent.config import get_effective_volumes
    from suzent.core.repository_context import (
        discover_skill_roots,
        resolve_repository_context,
    )

    configured_volumes = custom_volumes
    if configured_volumes is None and chat_id:
        from suzent.database import get_database

        chat = get_database().get_chat(chat_id)
        if chat:
            configured_volumes = list((chat.config or {}).get("sandbox_volumes") or [])
    effective_volumes = get_effective_volumes(configured_volumes or [])
    roots = resolve_repository_context(
        chat_id,
        cwd,
        custom_volumes=effective_volumes,
    )
    return SkillManager(
        discovered_roots=discover_skill_roots(roots),
        existing_volumes=effective_volumes,
        project_dir=roots.project_dir,
        sandbox_enabled=sandbox_enabled,
    )
