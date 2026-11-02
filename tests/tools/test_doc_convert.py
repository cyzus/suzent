"""read_file document conversion (tools/filesystem/doc_convert.py).

Fixtures are built in the test with the same libraries (or by hand for
formats with no writer installed), so no binary files live in the repo.
"""

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.tools.base import ToolErrorCode
from suzent.tools.filesystem import doc_convert
from suzent.tools.filesystem.read_file_tool import ReadFileTool


class _Resolver:
    def resolve(self, path):
        return Path(path)


def _read(tmp_path, path, **kwargs):
    deps = SimpleNamespace(
        path_resolver=_Resolver(),
        chat_id="test-chat",
        sandbox_enabled=False,
        custom_volumes=[],
        workspace_root=str(tmp_path),
    )
    return ReadFileTool().forward(SimpleNamespace(deps=deps), str(path), **kwargs)


# ─── Fixture builders ────────────────────────────────────────────────


def _pdf(path: Path, text: str) -> Path:
    """A minimal one-page PDF with a single line of Helvetica text."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(bytes(out))
    return path


def _docx(path: Path) -> Path:
    """A minimal DOCX: one heading and one paragraph."""
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    document = (
        f"<w:document {ns}><w:body>"
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>Quarterly Report</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Revenue grew by twelve percent.</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    styles = (
        f"<w:styles {ns}>"
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        '<w:name w:val="heading 1"/></w:style></w:styles>'
    )
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    doc_rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
    return path


def _pptx(path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
    slide.shapes.title.text = "Roadmap"
    table = slide.shapes.add_table(
        2, 2, Inches(1), Inches(2), Inches(4), Inches(1)
    ).table
    table.cell(0, 0).text, table.cell(0, 1).text = "Phase", "Owner"
    table.cell(1, 0).text, table.cell(1, 1).text = "Beta", "Suzy"
    slide.notes_slide.notes_text_frame.text = "Mention the store build"
    prs.save(str(path))
    return path


def _xlsx(path: Path, rows: int = 3) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Prices"
    ws.append(["Ticker", "Price"])
    for i in range(rows - 1):
        ws.append([f"T{i}", 100 + i])
    wb.create_sheet("Empty")
    wb.save(str(path))
    return path


def _epub(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
        )
        z.writestr(
            "OEBPS/content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<metadata><dc:title>Robot Poems</dc:title></metadata>"
            '<manifest><item id="c2" href="c2.xhtml"/><item id="c1" href="c1.xhtml"/>'
            "</manifest>"
            '<spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>',
        )
        z.writestr(
            "OEBPS/c1.xhtml", "<html><body><h1>One</h1><p>Gears</p></body></html>"
        )
        z.writestr(
            "OEBPS/c2.xhtml", "<html><body><h1>Two</h1><p>Sparks</p></body></html>"
        )
    return path


def _ipynb(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": ["# Analysis"]},
                    {"cell_type": "code", "source": ["print(1 + 1)"]},
                ],
                "metadata": {"language_info": {"name": "python"}},
            }
        ),
        encoding="utf-8",
    )
    return path


# ─── Tests ───────────────────────────────────────────────────────────


def test_pdf(tmp_path):
    result = _read(tmp_path, _pdf(tmp_path / "a.pdf", "Hello Suzent"))
    assert result.success, result.message
    assert "Hello Suzent" in result.message
    assert result.metadata["format"] == ".pdf"


def test_docx_keeps_headings(tmp_path):
    result = _read(tmp_path, _docx(tmp_path / "a.docx"))
    assert result.success, result.message
    assert "# Quarterly Report" in result.message
    assert "Revenue grew by twelve percent." in result.message


def test_pptx_title_table_and_notes(tmp_path):
    result = _read(tmp_path, _pptx(tmp_path / "a.pptx"))
    assert result.success, result.message
    assert "<!-- Slide number: 1 -->" in result.message
    assert "# Roadmap" in result.message
    assert "| Phase | Owner |" in result.message
    assert "| Beta | Suzy |" in result.message
    assert "Mention the store build" in result.message


def test_pptx_groups_charts_and_missing_notes_placeholder(tmp_path):
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    group = slide.shapes.add_group_shape()
    box = group.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    box.text_frame.text = "Grouped caption"
    data = CategoryChartData()
    data.categories = ["Q1", "Q2"]
    data.add_series("Revenue", (10, 12.5))
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(3), Inches(4), Inches(3), data
    ).chart
    chart.has_title = True
    chart.chart_title.text_frame.text = "Sales"
    # A notes slide whose text placeholder was deleted.
    placeholder = slide.notes_slide.notes_placeholder
    placeholder._element.getparent().remove(placeholder._element)
    path = tmp_path / "deck.pptx"
    prs.save(str(path))

    result = _read(tmp_path, path)

    assert result.success, result.message
    assert "Grouped caption" in result.message
    assert "### Chart: Sales" in result.message
    assert "| Category | Revenue |" in result.message
    assert "| Q1 | 10 |" in result.message
    assert "| Q2 | 12.5 |" in result.message


def test_pptx_picture_alt_text(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08"
        b"\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00"
        b"\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    image = tmp_path / "dot.png"
    image.write_bytes(png)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    picture = slide.shapes.add_picture(str(image), Inches(1), Inches(1))
    picture._element._nvXxPr.cNvPr.set("descr", "Org chart [draft]")
    path = tmp_path / "pic.pptx"
    prs.save(str(path))

    result = _read(tmp_path, path)

    assert "![Org chart draft](" in result.message


def test_xls_cells_are_typed(tmp_path):
    import xlrd
    from xlrd.sheet import Cell

    value = doc_convert._xls_value
    assert value(Cell(xlrd.XL_CELL_DATE, 45658.0), 0) == "2025-01-01"
    assert value(Cell(xlrd.XL_CELL_DATE, 0.5), 0) == "12:00:00"
    assert value(Cell(xlrd.XL_CELL_DATE, 45658.25), 0) == "2025-01-01 06:00:00"
    assert value(Cell(xlrd.XL_CELL_BOOLEAN, 1), 0) is True
    assert value(Cell(xlrd.XL_CELL_ERROR, 0x07), 0) == "#DIV/0!"
    assert value(Cell(xlrd.XL_CELL_EMPTY, ""), 0) is None
    assert value(Cell(xlrd.XL_CELL_NUMBER, 3.0), 0) == 3.0
    assert doc_convert.markdown_table([["d", "ok"], ["2025-01-01", True]]) == (
        "| d | ok |\n| --- | --- |\n| 2025-01-01 | True |"
    )


def test_xlsx_sheets_as_tables(tmp_path):
    result = _read(tmp_path, _xlsx(tmp_path / "a.xlsx"))
    assert result.success, result.message
    assert "## Prices" in result.message
    assert "| Ticker | Price |" in result.message
    assert "| T1 | 101 |" in result.message
    assert "## Empty" in result.message


def test_xlsx_row_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_convert, "MAX_SHEET_ROWS", 5)
    result = _read(tmp_path, _xlsx(tmp_path / "big.xlsx", rows=50))
    assert "[Sheet truncated after 5 rows]" in result.message
    assert "T10" not in result.message


def test_ipynb(tmp_path):
    result = _read(tmp_path, _ipynb(tmp_path / "n.ipynb"))
    assert result.success, result.message
    assert "# Analysis" in result.message
    assert "```python" in result.message
    assert "print(1 + 1)" in result.message


def test_epub_follows_spine_order(tmp_path):
    result = _read(tmp_path, _epub(tmp_path / "b.epub"))
    assert result.success, result.message
    text = result.message
    assert "# Robot Poems" in text
    assert text.index("Gears") < text.index("Sparks")


def test_ipynb_fences_cannot_be_closed_by_cell_contents(tmp_path):
    path = tmp_path / "fence.ipynb"
    path.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "raw", "source": "```python\nprint(1)\n```"},
                    {"cell_type": "code", "source": "s = '````'"},
                    {"cell_type": "markdown", "source": "# Next section"},
                ],
                "metadata": {"language_info": {"name": "python"}},
            }
        ),
        encoding="utf-8",
    )
    text = doc_convert.convert(path)

    assert "````\n```python\nprint(1)\n```\n````" in text
    assert "`````python\ns = '````'\n`````" in text
    # The heading after them is outside every fence.
    tail = text.split("# Next section")[0]
    import re

    opens = [len(m) for m in re.findall(r"^(`{3,})", tail, flags=re.M)]
    assert len(opens) % 2 == 0


def test_ipynb_raw_cell_is_fenced(tmp_path):
    path = tmp_path / "r.ipynb"
    path.write_text(
        json.dumps({"cells": [{"cell_type": "raw", "source": ["# not a heading"]}]}),
        encoding="utf-8",
    )
    assert doc_convert.convert(path) == "```\n# not a heading\n```"


def test_epub_includes_authors_and_language(tmp_path):
    path = tmp_path / "m.epub"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="content.opf"/></rootfiles>'
            "</container>",
        )
        z.writestr(
            "content.opf",
            '<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata>'
            "<dc:title>T</dc:title><dc:creator>Ann</dc:creator>"
            "<dc:creator>Bob</dc:creator><dc:language>en</dc:language>"
            "</metadata><manifest/><spine/></package>",
        )
    text = doc_convert.convert(path)
    assert "**Authors:** Ann, Bob" in text
    assert "**Language:** en" in text


def test_xlsx_dates_booleans_formulas_and_gaps(tmp_path):
    import datetime as dt

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["name", "when", "flag"])
    ws.append(["apple", dt.date(2026, 1, 15), True])
    ws.append([])
    ws.append(["cherry", None, None, None, "farcol"])
    path = tmp_path / "t.xlsx"
    wb.save(str(path))
    text = doc_convert.convert(path)
    assert "| apple | 2026-01-15 00:00:00 | True |" in text
    assert "farcol" in text
    assert "NaN" not in text and "Unnamed" not in text


def test_zip_lists_and_converts_members(tmp_path):
    inner = _ipynb(tmp_path / "n.ipynb")
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(inner, "notebooks/n.ipynb")
        z.writestr("data/raw.bin", b"\x00\x01")
    result = _read(tmp_path, archive)
    assert result.success, result.message
    assert "- notebooks/n.ipynb" in result.message
    assert "- data/raw.bin" in result.message
    assert "## notebooks/n.ipynb" in result.message
    assert "print(1 + 1)" in result.message


def test_zip_skips_oversized_members(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_convert, "MAX_ZIP_MEMBER_BYTES", 10)
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(_ipynb(tmp_path / "n.ipynb"), "n.ipynb")
    result = _read(tmp_path, archive)
    assert "(skipped: too large)" in result.message
    assert "print(1 + 1)" not in result.message


def test_epub_decodes_hrefs_and_skips_missing_chapters(tmp_path):
    path = tmp_path / "c.epub"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="content.opf"/></rootfiles>'
            "</container>",
        )
        z.writestr(
            "content.opf",
            "<package><manifest>"
            '<item id="a" href="chapter%201.xhtml#start"/>'
            '<item id="b" href="missing.xhtml"/></manifest>'
            '<spine><itemref idref="a"/><itemref idref="b"/></spine></package>',
        )
        z.writestr("chapter 1.xhtml", "<html><body><p>Hello</p></body></html>")
    result = _read(tmp_path, path)
    assert result.success, result.message
    assert "Hello" in result.message


def test_converted_output_is_paginated_like_text(tmp_path):
    path = _xlsx(tmp_path / "a.xlsx", rows=10)
    result = _read(tmp_path, path, offset=3, limit=2)
    assert result.success
    assert result.message.startswith("[Lines 3-4 of ")
    assert result.metadata["start_line"] == 3
    assert result.metadata["end_line"] == 4
    assert result.metadata["truncated"] is True


def test_unknown_text_extension_reads_as_text(tmp_path):
    path = tmp_path / "main.rs"
    path.write_text('fn main() { println!("hi"); }\n', encoding="utf-8")
    result = _read(tmp_path, path)
    assert result.success
    assert "1\tfn main()" in result.message


def test_unknown_binary_extension_is_rejected(tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    result = _read(tmp_path, path)
    assert not result.success
    assert result.error_code == ToolErrorCode.BINARY_FILE
    assert ".pdf" in result.message


def test_corrupt_document_reports_error(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip")
    result = _read(tmp_path, path)
    assert not result.success
    assert result.error_code == ToolErrorCode.EXECUTION_FAILED
    assert "Error converting file" in result.message


def test_missing_library_is_reported(tmp_path, monkeypatch):
    def _missing(path):
        raise ModuleNotFoundError("No module named 'pptx'", name="pptx")

    monkeypatch.setitem(doc_convert.CONVERTERS, ".pptx", _missing)
    path = tmp_path / "a.pptx"
    path.write_bytes(b"x")
    result = _read(tmp_path, path)
    assert not result.success
    assert "missing library (pptx)" in result.message


@pytest.mark.parametrize(
    "rows, expected",
    [
        ([["a", "b"], [1, 2.0]], "| a | b |\n| --- | --- |\n| 1 | 2 |"),
        ([["x|y", None, None]], "| x\\|y |\n| --- |"),
        ([], ""),
    ],
)
def test_markdown_table(rows, expected):
    assert doc_convert.markdown_table(rows) == expected
