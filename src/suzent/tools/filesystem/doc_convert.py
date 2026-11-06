"""Convert office documents to markdown for ``read_file``.

Each format calls its own small library directly (pdfminer.six, mammoth,
python-pptx, openpyxl, xlrd, olefile). This replaces MarkItDown, whose
mandatory file-type detector (magika -> onnxruntime -> sympy) and pandas-based
spreadsheet path added ~170 MB to the environment for the same output.

Every converter is imported lazily so a missing optional library only breaks
its own format.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

# Cap on sheet rows / zip members so one huge file cannot flood the context.
MAX_SHEET_ROWS = 5000
MAX_ZIP_MEMBERS = 200
# Members are decompressed into memory; skip any bigger than read_file's own
# 50 MiB limit (and so any zip bomb).
MAX_ZIP_MEMBER_BYTES = 50 * 1024 * 1024


class UnsupportedFormat(Exception):
    """The file is not a format this module converts."""


# ─── Helpers ─────────────────────────────────────────────────────────


def _cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def markdown_table(rows: Iterable[Iterable[object]]) -> str:
    """Render rows as a markdown table; the first row is the header."""
    cells = [[_cell(v) for v in row] for row in rows]
    # Drop fully empty trailing rows/columns that spreadsheets often carry.
    cells = [row for row in cells if any(row)]
    if not cells:
        return ""
    width = max(len(row) for row in cells)
    while width and not any(len(row) >= width and row[width - 1] for row in cells):
        width -= 1
    if width == 0:
        return ""
    cells = [(row + [""] * width)[:width] for row in cells]
    lines = ["| " + " | ".join(cells[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(row) + " |" for row in cells[1:]]
    return "\n".join(lines)


def _html_to_markdown(html: str) -> str:
    from markdownify import markdownify

    return markdownify(html, heading_style="ATX", strip=["img"]).strip()


# ─── Converters ──────────────────────────────────────────────────────


def convert_pdf(path: Path) -> str:
    from pdfminer.high_level import extract_text

    return extract_text(str(path))


def convert_docx(path: Path) -> str:
    import mammoth

    with path.open("rb") as f:
        result = mammoth.convert_to_html(f)
    return _html_to_markdown(result.value)


def _reading_order(shapes) -> list:
    """Top to bottom, then left to right (shapes without a position first)."""
    return sorted(
        shapes,
        key=lambda s: (
            float("-inf") if s.top is None else s.top,
            float("-inf") if s.left is None else s.left,
        ),
    )


def _chart_markdown(chart) -> str:
    """A chart as its title plus a Category x Series table of values."""
    try:
        heading = "### Chart"
        if chart.has_title and chart.chart_title.has_text_frame:
            heading += f": {chart.chart_title.text_frame.text}"
        categories = list(chart.plots[0].categories)
        series = list(chart.series)
        rows: list[list[object]] = [["Category", *(s.name for s in series)]]
        for index, category in enumerate(categories):
            rows.append(
                [
                    category,
                    *(
                        s.values[index] if index < len(s.values) else None
                        for s in series
                    ),
                ]
            )
        return f"{heading}\n\n{markdown_table(rows)}"
    except Exception:  # unsupported plot types raise from python-pptx
        return "[unsupported chart]"


def _shape_parts(shape, title) -> list[str]:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        return [
            part
            for child in _reading_order(shape.shapes)
            for part in _shape_parts(child, title)
        ]
    if getattr(shape, "has_chart", False) and shape.has_chart:
        return [_chart_markdown(shape.chart)]
    if getattr(shape, "has_table", False) and shape.has_table:
        rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
        table = markdown_table(rows)
        return [table] if table else []
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE or (
        shape.shape_type == MSO_SHAPE_TYPE.PLACEHOLDER and hasattr(shape, "image")
    ):
        try:
            alt = shape._element._nvXxPr.cNvPr.attrib.get("descr", "")
        except Exception:
            alt = ""
        alt = " ".join((alt or shape.name).replace("[", " ").replace("]", " ").split())
        return [f"![{alt}]({''.join(c for c in shape.name if c.isalnum())}.jpg)"]
    if shape.has_text_frame:
        text = shape.text_frame.text.strip()
        if text:
            return [f"# {text}" if shape == title else text]
    return []


def convert_pptx(path: Path) -> str:
    from pptx import Presentation

    parts: list[str] = []
    for number, slide in enumerate(Presentation(str(path)).slides, start=1):
        parts.append(f"<!-- Slide number: {number} -->")
        title = slide.shapes.title
        for shape in _reading_order(slide.shapes):
            parts.extend(_shape_parts(shape, title))
        if slide.has_notes_slide:
            # A notes slide can lack its text placeholder.
            frame = slide.notes_slide.notes_text_frame
            notes = frame.text.strip() if frame is not None else ""
            if notes:
                parts.append(f"### Notes:\n{notes}")
        parts.append("")
    return "\n\n".join(parts)


def _sheet_markdown(name: str, rows: Iterable[Iterable[object]]) -> str:
    limited: list[list[object]] = []
    truncated = False
    for index, row in enumerate(rows):
        if index >= MAX_SHEET_ROWS:
            truncated = True
            break
        limited.append(list(row))
    body = markdown_table(limited) or "(empty sheet)"
    if truncated:
        body += f"\n\n[Sheet truncated after {MAX_SHEET_ROWS} rows]"
    return f"## {name}\n\n{body}"


def convert_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(str(path), read_only=True, data_only=True)
    try:
        return "\n\n".join(
            _sheet_markdown(sheet.title, sheet.iter_rows(values_only=True))
            for sheet in workbook.worksheets
        )
    finally:
        workbook.close()


def _xls_value(cell, datemode: int) -> object:
    """A legacy-Excel cell as what it means, not its raw storage."""
    import xlrd

    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            value = xlrd.xldate_as_datetime(cell.value, datemode)
        except (ValueError, OverflowError, xlrd.xldate.XLDateError):
            return cell.value
        # A whole-day value is a date; a value under one day is a time.
        if cell.value == int(cell.value):
            return value.date().isoformat()
        if cell.value < 1:
            return value.time().isoformat()
        return value.isoformat(sep=" ")
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code.get(cell.value, "#ERROR")
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return None
    return cell.value


def convert_xls(path: Path) -> str:
    import xlrd

    book = xlrd.open_workbook(str(path))
    return "\n\n".join(
        _sheet_markdown(
            sheet.name,
            (
                [_xls_value(cell, book.datemode) for cell in sheet.row(i)]
                for i in range(sheet.nrows)
            ),
        )
        for sheet in book.sheets()
    )


def convert_msg(path: Path) -> str:
    import olefile

    def stream(msg, name: str) -> str | None:
        if not msg.exists(name):
            return None
        data = msg.openstream(name).read()
        for encoding in ("utf-16-le", "utf-8"):
            try:
                return data.decode(encoding).strip("\x00").strip()
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace").strip()

    msg = olefile.OleFileIO(str(path))
    try:
        lines = ["# Email Message", ""]
        for label, name in (
            ("From", "__substg1.0_0C1F001F"),
            ("To", "__substg1.0_0E04001F"),
            ("Subject", "__substg1.0_0037001F"),
        ):
            value = stream(msg, name)
            if value:
                lines.append(f"**{label}:** {value}")
        lines += ["", "## Content", "", stream(msg, "__substg1.0_1000001F") or ""]
        return "\n".join(lines).strip()
    finally:
        msg.close()


def _fenced(text: str, info: str = "") -> str:
    """``text`` in a code fence longer than any backtick run inside it, so a
    fenced example within the cell cannot close the block early."""
    import re

    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{info}\n{text}\n{fence}"


def convert_ipynb(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    language = (
        notebook.get("metadata", {}).get("language_info", {}).get("name", "python")
    )
    parts: list[str] = []
    for cell in notebook.get("cells", []):
        source = cell.get("source", "")
        text = "".join(source) if isinstance(source, list) else str(source)
        if not text.strip():
            continue
        if cell.get("cell_type") == "code":
            parts.append(_fenced(text, language))
        elif cell.get("cell_type") == "raw":
            # Raw cells are verbatim text, not markdown to be rendered.
            parts.append(_fenced(text))
        else:
            parts.append(text)
    return "\n\n".join(parts)


def convert_epub(path: Path) -> str:
    """Chapters in spine order, each converted from XHTML."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(
            el.attrib["full-path"]
            for el in container.iter()
            if el.tag.endswith("rootfile")
        )
        opf = ET.fromstring(archive.read(rootfile))
        base = PurePosixPath(rootfile).parent

        def children(tag: str):
            return [el for el in opf.iter() if el.tag.endswith(tag)]

        manifest = {
            el.attrib.get("id"): el.attrib.get("href") for el in children("item")
        }
        title = next((el.text for el in children("title") if el.text), None)
        parts = [f"# {title}"] if title else []
        meta = [
            f"**{label}:** {', '.join(values)}"
            for label, tag in (("Authors", "creator"), ("Language", "language"))
            if (values := [el.text.strip() for el in children(tag) if el.text])
        ]
        if meta:
            parts.append("\n".join(meta))
        for ref in children("itemref"):
            href = manifest.get(ref.attrib.get("idref"))
            if not href:
                continue
            # Manifest hrefs are URL-encoded and may carry a #fragment.
            member = str(base / unquote(href.split("#", 1)[0]))
            try:
                html = archive.read(member).decode("utf-8", errors="replace")
            except KeyError:  # spine points at a file the archive lacks
                continue
            text = _html_to_markdown(html)
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def convert_zip(path: Path) -> str:
    """List the archive and convert the members this module understands."""
    import tempfile

    parts = [f"# Archive: {path.name}"]
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        parts.append(
            "\n".join(f"- {m.filename} ({m.file_size} bytes)" for m in members)
        )
        with tempfile.TemporaryDirectory() as tmp:
            for member in members[:MAX_ZIP_MEMBERS]:
                suffix = PurePosixPath(member.filename).suffix.lower()
                if suffix not in CONVERTERS or suffix == ".zip":
                    continue
                if member.file_size > MAX_ZIP_MEMBER_BYTES:
                    parts.append(f"## {member.filename}\n\n(skipped: too large)")
                    continue
                target = Path(tmp) / f"member{suffix}"
                target.write_bytes(archive.read(member))
                try:
                    body = CONVERTERS[suffix](target)
                except Exception as e:  # one bad member must not sink the rest
                    body = f"(could not convert: {e})"
                parts.append(f"## {member.filename}\n\n{body.strip()}")
    return "\n\n".join(parts)


CONVERTERS: dict[str, Callable[[Path], str]] = {
    ".pdf": convert_pdf,
    ".docx": convert_docx,
    ".pptx": convert_pptx,
    ".xlsx": convert_xlsx,
    ".xlsm": convert_xlsx,
    ".xls": convert_xls,
    ".msg": convert_msg,
    ".ipynb": convert_ipynb,
    ".epub": convert_epub,
    ".zip": convert_zip,
}


def convert(path: Path) -> str:
    """Convert ``path`` to markdown, or raise :class:`UnsupportedFormat`."""
    converter = CONVERTERS.get(path.suffix.lower())
    if converter is None:
        raise UnsupportedFormat(path.suffix or path.name)
    return converter(path)
