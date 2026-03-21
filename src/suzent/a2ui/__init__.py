"""
A2UI — Agent-to-UI canvas rendering for Suzent.

Agents call render_ui() to push structured interactive surfaces
(tables, forms, cards, buttons) to the canvas panel in the frontend.
Surfaces are transported via AG-UI CUSTOM events over the existing SSE stream.
"""

from suzent.a2ui.models import (
    A2UIComponent,
    A2UISurface,
    A2UIText,
    A2UIBadge,
    A2UIButton,
    A2UITable,
    A2UITableColumn,
    A2UIForm,
    A2UIFormField,
    A2UIList,
    A2UIProgress,
    A2UIDivider,
    A2UICard,
    A2UIColumns,
    A2UIStack,
)

__all__ = [
    "A2UIComponent",
    "A2UISurface",
    "A2UIText",
    "A2UIBadge",
    "A2UIButton",
    "A2UITable",
    "A2UITableColumn",
    "A2UIForm",
    "A2UIFormField",
    "A2UIList",
    "A2UIProgress",
    "A2UIDivider",
    "A2UICard",
    "A2UIColumns",
    "A2UIStack",
]
