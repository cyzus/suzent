"""Turn a canvas surface into a standalone HTML file.

A saved canvas is a snapshot for reading, so buttons and forms, which only
talk back to the chat that drew them, are left out.
"""

import hashlib
import re
from html import escape
from pathlib import Path

from suzent.core.library_index import ARTIFACTS_DIRNAME
from suzent.a2ui.models import (
    A2UIBadge,
    A2UICard,
    A2UIColumns,
    A2UIComponent,
    A2UIDivider,
    A2UIHtml,
    A2UIList,
    A2UIProgress,
    A2UIStack,
    A2UISurface,
    A2UITable,
    A2UIText,
)

CANVAS_DIRNAME = "canvas"

_STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0; padding: 32px; color: #111; background: #fff; line-height: 1.5; }
main { max-width: 960px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
h1 { font-size: 24px; margin: 0 0 8px; text-transform: uppercase; letter-spacing: -0.02em; }
h2 { font-size: 18px; margin: 0; } h3 { font-size: 15px; margin: 0; }
.caption { color: #666; font-size: 12px; } p { margin: 0; white-space: pre-wrap; }
pre { background: #f5f5f5; padding: 12px; overflow-x: auto; margin: 0; }
.card { border: 2px solid #000; box-shadow: 4px 4px 0 #000; padding: 16px;
  display: flex; flex-direction: column; gap: 12px; }
.stack { display: flex; flex-direction: column; } .columns { display: flex; gap: 16px; }
.columns > * { min-width: 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { border: 2px solid #000; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
.badge { display: inline-block; border: 2px solid #000; padding: 0 6px; font-size: 12px;
  font-weight: 700; width: fit-content; }
.success { background: #A8E6A3; } .warning { background: #FFE666; }
.error { background: #FFD7D7; } .info { background: #D6E4FF; }
.bar { border: 2px solid #000; height: 12px; } .bar > div { background: #000; height: 100%; }
hr { border: 0; border-top: 2px solid #000; width: 100%; margin: 0; }
iframe { width: 100%; min-height: 360px; border: 2px solid #000; }
"""

_GAPS = {"sm": 8, "md": 16, "lg": 24}


def _render(component: A2UIComponent) -> str:
    match component:
        case A2UIText(variant="heading"):
            return f"<h2>{escape(component.content)}</h2>"
        case A2UIText(variant="subheading"):
            return f"<h3>{escape(component.content)}</h3>"
        case A2UIText(variant="caption"):
            return f'<p class="caption">{escape(component.content)}</p>'
        case A2UIText(variant="code"):
            return f"<pre><code>{escape(component.content)}</code></pre>"
        case A2UIText():
            return f"<p>{escape(component.content)}</p>"
        case A2UIBadge():
            return f'<span class="badge {component.color}">{escape(component.label)}</span>'
        case A2UITable():
            head = "".join(f"<th>{escape(c.label)}</th>" for c in component.columns)
            rows = "".join(
                "<tr>"
                + "".join(
                    f"<td>{escape(str(row.get(c.key, '')))}</td>"
                    for c in component.columns
                )
                + "</tr>"
                for row in component.rows
            )
            return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
        case A2UIList():
            tag = "ol" if component.ordered else "ul"
            items = "".join(f"<li>{escape(item)}</li>" for item in component.items)
            return f"<{tag}>{items}</{tag}>"
        case A2UIProgress():
            value = max(0.0, min(100.0, component.value))
            label = escape(component.label or "")
            label = f"<p>{label} <strong>{value:g}%</strong></p>"
            return f'{label}<div class="bar"><div style="width:{value:g}%"></div></div>'
        case A2UIDivider():
            return "<hr>"
        case A2UIHtml():
            return (
                f'<iframe sandbox="allow-scripts" srcdoc="{escape(component.html)}"'
                f' style="height:{component.height or 480}px"></iframe>'
            )
        case A2UICard():
            title = f"<h2>{escape(component.title)}</h2>" if component.title else ""
            inner = "".join(_render(child) for child in component.children)
            return f'<section class="card">{title}{inner}</section>'
        case A2UIColumns():
            ratios = (component.ratios or []) + [1.0] * len(component.children)
            cells = "".join(
                f'<div style="flex:{ratio:g}">{_render(child)}</div>'
                for child, ratio in zip(component.children, ratios)
            )
            return f'<div class="columns">{cells}</div>'
        case A2UIStack():
            inner = "".join(_render(child) for child in component.children)
            return (
                f'<div class="stack" style="gap:{_GAPS[component.gap]}px">{inner}</div>'
            )
    return ""


def surface_to_html(surface: A2UISurface) -> str:
    """A self-contained page showing *surface* as it read when saved."""
    title = surface.title or surface.id
    if isinstance(surface.component, A2UIHtml):
        html = surface.component.html
        return (
            html
            if re.match(r"\s*<!doctype\s", html, re.I)
            else f"<!DOCTYPE html>\n{html}"
        )
    return (
        '<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main><h1>{escape(title)}</h1>{_render(surface.component)}</main></body></html>\n"
    )


def canvas_file_name(surface: A2UISurface, chat_id: str) -> str:
    """Stable per chat and surface, so saving again replaces only that surface's file."""
    stem = re.sub(r"[^\w-]+", "-", (surface.title or surface.id).strip().lower()).strip(
        "-"
    )
    tag = hashlib.sha1(f"{chat_id}:{surface.id}".encode()).hexdigest()[:6]
    return f"{stem[:80] or 'canvas'}-{tag}.html"


def save_surface(surface: A2UISurface, chat_id: str, project_dir: Path) -> Path:
    """Write *surface* under the project library's ``artifacts/canvas/``."""
    target = (
        project_dir
        / ARTIFACTS_DIRNAME
        / CANVAS_DIRNAME
        / canvas_file_name(surface, chat_id)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(surface_to_html(surface), encoding="utf-8")
    return target
