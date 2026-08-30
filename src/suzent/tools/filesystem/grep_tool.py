"""
GrepTool - Search file contents with regex.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, List, Optional, Tuple

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

from suzent.logger import get_logger
from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.tools.filesystem.path_resolver import DEFAULT_PRUNED_DIRS, PathResolver

logger = get_logger(__name__)

MAX_GREP_FILE_SIZE = 2 * 1024 * 1024  # 2 MiB
MAX_GREP_FILES_SCANNED = 5000
RIPGREP_TIMEOUT_SECONDS = 10
RIPGREP_OUTPUT_LIMIT = 2 * 1024 * 1024
# Shared with find_files' walk pruning; kept here as a defense for the case
# where the caller explicitly targets a path inside a pruned dir.
DEFAULT_EXCLUDED_DIRS = DEFAULT_PRUNED_DIRS


class GrepTool(Tool):
    """
    Search file contents with regex.
    """

    name = "GrepTool"
    tool_name = "grep_search"
    group = ToolGroup.FILESYSTEM

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver: Optional[PathResolver] = None
        self._ripgrep_path: Optional[str] = None
        self._ripgrep_checked = False

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        pattern: Annotated[
            str,
            Field(
                description="Regex pattern to search for. This must be valid regular expression syntax."
            ),
        ],
        path: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional file or directory search root. Leave empty to search the current workspace root.",
            ),
        ] = None,
        include: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional glob filter for files to include, such as '*.py' or '*.{js,ts}'.",
            ),
        ] = None,
        case_insensitive: Annotated[
            Optional[bool],
            Field(
                default=None,
                description="Set to true for case-insensitive regex matching.",
            ),
        ] = None,
        context_lines: Annotated[
            Optional[int],
            Field(
                default=None,
                ge=0,
                description="Number of surrounding lines to include around each match.",
            ),
        ] = None,
    ) -> ToolResult:
        """Search file contents using a regex pattern.

        Searches through files for lines matching the given regular expression. Supports
        filtering by file type, case-insensitive matching, and showing context lines around
        matches.

        Args:
            ctx: The run context with agent dependencies.
            pattern: Regex pattern to search for.
            path: File or directory to search in (default: working directory).
            include: Filter files by glob pattern (e.g., '*.py', '*.{js,ts}').
            case_insensitive: If True, perform case-insensitive search.
            context_lines: Number of lines to show before and after each match.

        Returns:
            Matching lines grouped by file, or a message if no matches found.
        """
        deps = ctx.deps
        self._resolver = get_or_create_path_resolver(deps)

        try:
            # Compile regex
            flags = re.IGNORECASE if case_insensitive else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"Invalid regex pattern: {e}",
                    metadata={"pattern": pattern, "path": path, "include": include},
                )

            ripgrep_result = self._search_with_ripgrep(
                pattern=pattern,
                path=path,
                include=include,
                case_insensitive=bool(case_insensitive),
                context_lines=context_lines or 0,
            )
            if ripgrep_result is not None:
                results, files_with_matches, scanned_files, output_capped = (
                    ripgrep_result
                )
                return self._format_results(
                    pattern=pattern,
                    path=path,
                    include=include,
                    context_lines=context_lines or 0,
                    results=results,
                    files_with_matches=files_with_matches,
                    scanned_files=scanned_files,
                    skipped_large_files=0,
                    skipped_excluded_files=0,
                    capped=output_capped,
                    engine="ripgrep",
                )

            # Collect files to search
            glob_pattern = include or "**/*"

            # Use unified finder
            found_files = self._resolver.find_files(glob_pattern, path)

            # Search files
            results: List[Tuple[str, int, str]] = []  # (file, line_num, content)
            files_with_matches = 0
            ctx_lines = context_lines or 0
            scanned_files = 0
            skipped_large_files = 0
            skipped_excluded_files = 0
            capped = False

            for file_path, v_path in found_files:
                if len(results) >= 1000:  # Global safety limit
                    break

                if scanned_files >= MAX_GREP_FILES_SCANNED:
                    capped = True
                    break

                if not file_path.is_file() or not self._is_text_file(file_path):
                    continue

                if any(part in DEFAULT_EXCLUDED_DIRS for part in file_path.parts):
                    skipped_excluded_files += 1
                    continue

                try:
                    if file_path.stat().st_size > MAX_GREP_FILE_SIZE:
                        skipped_large_files += 1
                        continue
                except OSError:
                    continue

                scanned_files += 1

                try:
                    matches = self._search_file(file_path, regex, ctx_lines)
                    if matches:
                        files_with_matches += 1
                        # Return host path in host mode, virtual path in sandbox mode
                        display_path = (
                            str(file_path)
                            if not self._resolver.sandbox_enabled
                            else v_path
                        )
                        for line_num, content in matches:
                            results.append((display_path, line_num, content))
                except Exception as e:
                    logger.debug(f"Could not search {file_path}: {e}")

            return self._format_results(
                pattern=pattern,
                path=path,
                include=include,
                context_lines=ctx_lines,
                results=results,
                files_with_matches=files_with_matches,
                scanned_files=scanned_files,
                skipped_large_files=skipped_large_files,
                skipped_excluded_files=skipped_excluded_files,
                capped=capped,
                engine="python",
            )

        except ValueError as e:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                str(e),
                metadata={"pattern": pattern, "path": path, "include": include},
            )
        except Exception as e:
            logger.error(f"Error in grep: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                str(e),
                metadata={"pattern": pattern, "path": path, "include": include},
            )

    def _check_ripgrep_available(self) -> bool:
        if not self._ripgrep_checked:
            self._ripgrep_path = shutil.which("rg")
            self._ripgrep_checked = True
        return self._ripgrep_path is not None

    def _search_with_ripgrep(
        self,
        *,
        pattern: str,
        path: Optional[str],
        include: Optional[str],
        case_insensitive: bool,
        context_lines: int,
    ) -> Optional[tuple[List[Tuple[str, int, str]], int, int, bool]]:
        """Run ripgrep, returning None when the Python fallback should be used."""
        if (
            not self._check_ripgrep_available()
            or self._resolver is None
            or not hasattr(self._resolver, "resolve")
        ):
            return None

        if path == "/" and hasattr(self._resolver, "get_virtual_roots"):
            targets = []
            seen_targets: set[Path] = set()
            for _, root in self._resolver.get_virtual_roots():
                target = Path(root).resolve()
                if target.exists() and target not in seen_targets:
                    seen_targets.add(target)
                    targets.append(target)
        else:
            targets = [self._resolver.resolve(path or ".")]

        if not targets:
            return [], 0, 0, False

        args = [
            self._ripgrep_path or "rg",
            "--json",
            "--line-number",
            "--color",
            "never",
            "--hidden",
            "--no-ignore",
            "--max-filesize",
            "2M",
        ]
        if include:
            args.extend(["--glob", include])
        for excluded_dir in sorted(DEFAULT_EXCLUDED_DIRS):
            args.extend(["--glob", f"!**/{excluded_dir}/**"])
        if case_insensitive:
            args.append("--ignore-case")
        if context_lines:
            args.extend(["--context", str(context_lines)])
        args.extend(["--", pattern, *(str(target) for target in targets)])

        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                timeout=RIPGREP_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(f"ripgrep unavailable during search; using Python: {exc}")
            return None

        if completed.returncode not in (0, 1):
            logger.warning(
                "ripgrep rejected or failed the search; using Python fallback"
            )
            return None

        output = completed.stdout
        output_capped = len(output.encode("utf-8")) > RIPGREP_OUTPUT_LIMIT
        if output_capped:
            output = output.encode("utf-8")[:RIPGREP_OUTPUT_LIMIT].decode(
                "utf-8", errors="ignore"
            )

        results: List[Tuple[str, int, str]] = []
        matched_files: set[str] = set()
        scanned_files = 0
        for raw_line in output.splitlines():
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            data = event.get("data", {})
            if event_type == "summary":
                scanned_files = int(data.get("stats", {}).get("searches", 0))
                continue
            if event_type not in {"match", "context"}:
                continue

            raw_path = data.get("path", {}).get("text")
            line_number = data.get("line_number")
            text = data.get("lines", {}).get("text")
            if not raw_path or not line_number or text is None:
                continue
            host_path = Path(raw_path).resolve()
            display_path = str(host_path)
            if self._resolver.sandbox_enabled:
                display_path = self._resolver.to_virtual_path(host_path) or display_path
            if event_type == "match":
                matched_files.add(display_path)
                if context_lines:
                    text = f"> {text}"
            elif context_lines:
                text = f"  {text}"
            results.append((display_path, int(line_number), text))
            if len(results) >= 1000:
                output_capped = True
                break

        return results, len(matched_files), scanned_files, output_capped

    @staticmethod
    def _format_results(
        *,
        pattern: str,
        path: Optional[str],
        include: Optional[str],
        context_lines: int,
        results: List[Tuple[str, int, str]],
        files_with_matches: int,
        scanned_files: int,
        skipped_large_files: int,
        skipped_excluded_files: int,
        capped: bool,
        engine: str,
    ) -> ToolResult:
        metadata = {
            "match_count": len(results),
            "file_count": files_with_matches,
            "scanned_files": scanned_files,
            "skipped_large_files": skipped_large_files,
            "skipped_excluded_files": skipped_excluded_files,
            "capped": capped,
            "pattern": pattern,
            "path": path,
            "include": include,
            "context_lines": context_lines,
            "engine": engine,
        }
        if not results:
            message = f"No matches for '{pattern}' in {path or 'working directory'}"
            if capped:
                if engine == "python":
                    message += (
                        f" (scan capped at {MAX_GREP_FILES_SCANNED} files; "
                        "use 'include' or a narrower 'path' to speed up search)"
                    )
                else:
                    message += " (search output was capped; narrow 'path' or 'include')"
            return ToolResult.success_result(message, metadata=metadata)

        output_lines = [
            f"Found {len(results)} match(es) in {files_with_matches} file(s):"
        ]
        current_file = None
        for display_path, line_number, content in results[:50]:
            if display_path != current_file:
                output_lines.append(f"\n{display_path}:")
                current_file = display_path
            output_lines.append(f"  {line_number}: {content.rstrip()}")
        if len(results) > 50:
            output_lines.append(f"\n... and {len(results) - 50} more matches")
        return ToolResult.success_result("\n".join(output_lines), metadata=metadata)

    def _is_text_file(self, path: Path) -> bool:
        """Check if file is likely a text file."""
        text_extensions = {
            ".txt",
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".csv",
            ".html",
            ".css",
            ".scss",
            ".sql",
            ".sh",
            ".bash",
            ".toml",
            ".ini",
            ".cfg",
            ".conf",
            ".log",
            ".xml",
            ".env",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".rb",
            ".php",
        }
        return path.suffix.lower() in text_extensions

    def _search_file(
        self, path: Path, regex: re.Pattern, context_lines: int
    ) -> List[Tuple[int, str]]:
        """Search a file and return matching lines."""
        matches = []

        if context_lines <= 0:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f):
                        if regex.search(line):
                            matches.append((i + 1, line))
            except Exception:
                return []
            return matches

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return []

        for i, line in enumerate(lines):
            if regex.search(line):
                if context_lines > 0:
                    # Include context
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    for j in range(start, end):
                        prefix = ">" if j == i else " "
                        matches.append((j + 1, f"{prefix} {lines[j]}"))
                    matches.append((0, "---"))  # Separator
                else:
                    matches.append((i + 1, line))

        # Remove trailing separator
        if matches and matches[-1][0] == 0:
            matches.pop()

        return matches
