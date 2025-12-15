"""
Input validation utilities for Suzent.

Provides validation for API inputs to prevent injection attacks and ensure data integrity.
"""
import re
from typing import Optional, Dict, Any, List
from pathlib import Path
from suzent.logger import get_logger

logger = get_logger(__name__)


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


def validate_chat_id(chat_id: str) -> str:
    """
    Validate chat ID format.
    
    Chat IDs should be alphanumeric with hyphens.
    """
    if not chat_id:
        raise ValidationError("Chat ID cannot be empty")
    
    if not re.match(r'^[a-zA-Z0-9\-_]+$', chat_id):
        raise ValidationError(
            "Chat ID can only contain letters, numbers, hyphens, and underscores"
        )
    
    if len(chat_id) > 100:
        raise ValidationError("Chat ID too long (max 100 characters)")
    
    return chat_id


def validate_chat_title(title: str) -> str:
    """Validate chat title."""
    if not title:
        raise ValidationError("Title cannot be empty")
    
    if len(title) > 200:
        raise ValidationError("Title too long (max 200 characters)")
    
    # Remove any control characters
    title = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title)
    
    return title.strip()


def validate_message_content(content: Any) -> Any:
    """
    Validate message content.
    
    Content can be:
    - String: text message
    - List: multipart message (text + images)
    """
    if isinstance(content, str):
        if len(content) > 100000:  # 100KB text limit
            raise ValidationError("Message content too long (max 100KB)")
        return content
    
    elif isinstance(content, list):
        # Multipart message validation
        if len(content) > 10:
            raise ValidationError("Too many message parts (max 10)")
        
        for part in content:
            if not isinstance(part, dict):
                raise ValidationError("Message parts must be dictionaries")
            
            part_type = part.get("type")
            if part_type not in ["text", "image_url"]:
                raise ValidationError(f"Invalid message part type: {part_type}")
            
            if part_type == "text":
                text = part.get("text", "")
                if len(text) > 100000:
                    raise ValidationError("Text part too long (max 100KB)")
            
            elif part_type == "image_url":
                # Basic URL validation
                url = part.get("image_url", {}).get("url", "")
                if not url.startswith(("http://", "https://", "data:")):
                    raise ValidationError("Invalid image URL format")
        
        return content
    
    else:
        raise ValidationError("Invalid message content type")


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate chat configuration."""
    if not isinstance(config, dict):
        raise ValidationError("Config must be a dictionary")
    
    # Validate model
    model = config.get("model")
    if model and not isinstance(model, str):
        raise ValidationError("Model must be a string")
    
    # Validate agent type
    agent = config.get("agent")
    if agent and agent not in ["ToolCallingAgent", "CodeAgent"]:
        raise ValidationError(f"Invalid agent type: {agent}")
    
    # Validate tools
    tools = config.get("tools", [])
    if not isinstance(tools, list):
        raise ValidationError("Tools must be a list")
    
    if len(tools) > 20:
        raise ValidationError("Too many tools (max 20)")
    
    for tool in tools:
        if not isinstance(tool, str):
            raise ValidationError("Tool names must be strings")
        if not re.match(r'^[a-zA-Z0-9_]+$', tool):
            raise ValidationError(f"Invalid tool name: {tool}")
    
    return config


def validate_file_path(path: str, allowed_base: Optional[Path] = None) -> Path:
    """
    Validate file path to prevent directory traversal attacks.
    
    Args:
        path: File path to validate
        allowed_base: Optional base directory to restrict access
    
    Returns:
        Validated Path object
    
    Raises:
        ValidationError: If path is invalid or outside allowed base
    """
    try:
        file_path = Path(path).resolve()
    except Exception as e:
        raise ValidationError(f"Invalid path: {e}")
    
    # Check for directory traversal
    if ".." in path:
        raise ValidationError("Path traversal not allowed")
    
    # Check against allowed base
    if allowed_base:
        allowed_base = Path(allowed_base).resolve()
        try:
            file_path.relative_to(allowed_base)
        except ValueError:
            raise ValidationError(f"Path outside allowed directory: {allowed_base}")
    
    return file_path


def validate_search_query(query: str) -> str:
    """Validate search query."""
    if not query:
        raise ValidationError("Search query cannot be empty")
    
    if len(query) > 500:
        raise ValidationError("Search query too long (max 500 characters)")
    
    # Remove control characters
    query = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', query)
    
    return query.strip()


def validate_pagination(limit: Optional[int], offset: Optional[int]) -> tuple:
    """Validate pagination parameters."""
    if limit is not None:
        if not isinstance(limit, int) or limit < 1:
            raise ValidationError("Limit must be a positive integer")
        if limit > 1000:
            raise ValidationError("Limit too large (max 1000)")
    else:
        limit = 50
    
    if offset is not None:
        if not isinstance(offset, int) or offset < 0:
            raise ValidationError("Offset must be a non-negative integer")
    else:
        offset = 0
    
    return limit, offset


def validate_url(url: str, allowed_schemes: Optional[List[str]] = None) -> str:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        allowed_schemes: List of allowed schemes (default: http, https)
    """
    if not url:
        raise ValidationError("URL cannot be empty")
    
    if len(url) > 2000:
        raise ValidationError("URL too long (max 2000 characters)")
    
    allowed_schemes = allowed_schemes or ["http", "https"]
    
    # Basic URL validation
    url_pattern = r'^([a-z]+)://[^\s/$.?#].[^\s]*$'
    if not re.match(url_pattern, url, re.IGNORECASE):
        raise ValidationError("Invalid URL format")
    
    # Check scheme
    scheme = url.split("://")[0].lower()
    if scheme not in allowed_schemes:
        raise ValidationError(f"URL scheme not allowed: {scheme}")
    
    return url


def sanitize_html(text: str) -> str:
    """
    Basic HTML sanitization for user-generated content.
    
    Note: Frontend already uses rehype-sanitize. This is a backup.
    """
    # Remove script tags
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove event handlers
    text = re.sub(r'\s*on\w+\s*=\s*["\'].*?["\']', '', text, flags=re.IGNORECASE)
    
    # Remove javascript: URLs
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    
    return text


def validate_plan_objective(objective: str) -> str:
    """Validate plan objective."""
    if not objective:
        raise ValidationError("Plan objective cannot be empty")
    
    if len(objective) > 500:
        raise ValidationError("Plan objective too long (max 500 characters)")
    
    return objective.strip()


def validate_task_description(description: str) -> str:
    """Validate task description."""
    if not description:
        raise ValidationError("Task description cannot be empty")
    
    if len(description) > 1000:
        raise ValidationError("Task description too long (max 1000 characters)")
    
    return description.strip()


def validate_task_status(status: str) -> str:
    """Validate task status."""
    valid_statuses = ["pending", "in_progress", "completed", "failed"]
    
    if status not in valid_statuses:
        raise ValidationError(
            f"Invalid task status: {status}. "
            f"Must be one of: {', '.join(valid_statuses)}"
        )
    
    return status
