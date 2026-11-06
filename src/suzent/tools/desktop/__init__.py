"""Host desktop control through the agent-desktop CLI.

The tool is registered by the optional ``desktop`` plugin. It is not part of
the default tool set.
"""

from suzent.tools.desktop.tool import DesktopTool

__all__ = ["DesktopTool"]
