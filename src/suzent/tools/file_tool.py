from pathlib import Path
from markitdown import MarkItDown
from smolagents.tools import Tool
from suzent.logger import get_logger

logger = get_logger(__name__)

class FileTool(Tool):
    """
    A tool for reading and converting various file formats to markdown.
    Supports PDF, Word, Excel, PowerPoint, images, HTML, text files, and more.
    """
    name = "FileTool"
    description = "Read and convert various file formats (PDF, DOCX, XLSX, PPTX, images, etc.) to markdown text."
    inputs = {
        "file_path": {
            "type": "string",
            "description": "The path to the file to read and convert to markdown."
        }
    }
    output_type = "string"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._converter = MarkItDown()

    def forward(self, file_path: str) -> str:
        """
        Converts a file to markdown text.

        Args:
            file_path: Path to the file to convert

        Returns:
            The file content converted to markdown format
        """
        try:
            path = Path(file_path)

            # Check if file exists
            if not path.exists():
                return f"Error: File not found: {file_path}"

            # Check if it's a file (not a directory)
            if not path.is_file():
                return f"Error: Path is not a file: {file_path}"

            # Convert the file to markdown
            logger.info(f"Converting file to markdown: {file_path}")
            result = self._converter.convert(str(path))

            # MarkItDown returns a result object with 'text_content' attribute
            if hasattr(result, 'text_content'):
                content = result.text_content
            else:
                content = str(result)

            if not content or not content.strip():
                return f"Warning: File converted but appears to be empty: {file_path}"

            logger.info(f"Successfully converted file: {file_path} ({len(content)} characters)")
            return content

        except Exception as e:
            logger.error(f"Error converting file {file_path}: {e}")
            return f"Error converting file: {e}"