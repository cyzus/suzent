"""
EditFileTool - Make precise string replacements in files.
"""

from typing import Optional

from smolagents.tools import Tool

from suzent.logger import get_logger
from suzent.tools.path_resolver import PathResolver

logger = get_logger(__name__)


class EditFileTool(Tool):
    """
    Make exact string replacements in files.
    """
    
    name = "EditFileTool"
    description = """Make exact string replacements in files.

Use this for precise edits. The old_string must match exactly (including whitespace).

For complete file rewrites, use WriteFileTool instead.

Examples:
- EditFileTool(file_path="script.py", old_string="def foo():", new_string="def bar():")
- EditFileTool(file_path="config.json", old_string='"debug": false', new_string='"debug": true')
- EditFileTool(file_path="data.txt", old_string="old", new_string="new", replace_all=True)
"""
    
    inputs = {
        "file_path": {
            "type": "string",
            "description": "Path to the file to edit"
        },
        "old_string": {
            "type": "string",
            "description": "Exact text to replace (must match exactly)"
        },
        "new_string": {
            "type": "string",
            "description": "Replacement text"
        },
        "replace_all": {
            "type": "boolean",
            "description": "Replace all occurrences (default: False, replaces first only)",
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver: Optional[PathResolver] = None
    
    def set_context(self, resolver: PathResolver) -> None:
        """Set the path resolver context."""
        self._resolver = resolver
    
    def forward(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: Optional[bool] = None
    ) -> str:
        """
        Replace text in a file.
        
        Args:
            file_path: Path to the file
            old_string: Text to replace
            new_string: Replacement text
            replace_all: Replace all occurrences (default: False)
            
        Returns:
            Success message with replacement count, or error
        """
        if not self._resolver:
            return "Error: EditFileTool not initialized. No resolver context."
        
        replace_all = replace_all or False
        
        try:
            # Resolve the path
            resolved_path = self._resolver.resolve(file_path)
            
            # Check if file exists
            if not resolved_path.exists():
                return f"Error: File not found: {file_path}"
            
            if not resolved_path.is_file():
                return f"Error: Path is not a file: {file_path}"
            
            # Read current content
            try:
                content = resolved_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                return "Error: Cannot edit binary files"
            
            # Check if old_string exists
            if old_string not in content:
                return f"Error: String not found in file: {repr(old_string[:50])}..."
            
            # Count occurrences
            count = content.count(old_string)
            
            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                replaced = count
            else:
                new_content = content.replace(old_string, new_string, 1)
                replaced = 1
            
            # Write back
            resolved_path.write_text(new_content, encoding='utf-8')
            
            logger.info(f"Edited {file_path}: {replaced} replacement(s)")
            
            if count > 1 and not replace_all:
                return f"Replaced 1 of {count} occurrences in {file_path}. Use replace_all=True for all."
            else:
                return f"Replaced {replaced} occurrence(s) in {file_path}"
            
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            return f"Error editing file: {str(e)}"
