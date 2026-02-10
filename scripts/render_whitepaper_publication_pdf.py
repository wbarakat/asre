#!/usr/bin/env python3
"""Render a publication-style PDF from the ASRE white-paper markdown."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import re
from pathlib import Path
from typing import List, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def split_title_and_body(lines: Sequence[str]) -> tuple[str, List[str]]:
    title = "Solving Admission Signal Reliability"
    start_idx = 0
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            start_idx = idx + 1
            break
    return title, list(lines[start_idx:])


def clean_reference_marks(text: str) -> str:
    return re.sub(r"\[\^(\d+)\]", r"[\1]", text)


def extract_exec_summary(body: Sequence[str]) -> str:
    in_section = False
    para_lines: List[str] = []

    for line in body:
        stripped = line.strip()

        if stripped.startswith("## "):
            if re.match(r"^##\s+1\.\s+Executive Summary", stripped):
                in_section = True
                continue
            if in_section:
                break

        if not in_section:
            continue

        if stripped in {"---", "***"}:
            continue

        if stripped:
            para_lines.append(stripped)
        elif para_lines:
            break

    if not para_lines:
        return ""
    return clean_reference_marks(" ".join(para_lines))


def markdown_inline_to_rml(text: str) -> str:
    text = clean_reference_marks(text)

    tokens: dict[str, str] = {}
    idx = 0

    def stash(pattern: str, opener: str, closer: str, source: str) -> str:
        nonlocal idx

        def repl(match: re.Match[str]) -> str:
            nonlocal idx
            key = f"@@TOKEN{idx}@@"
            idx += 1
            inner = html.escape(match.group(1))
            tokens[key] = f"{opener}{inner}{closer}"
            return key

        return re.sub(pattern, repl, source)

    # Markdown links first: [text](url)
    def link_repl(match: re.Match[str]) -> str:
        nonlocal idx
        key = f"@@TOKEN{idx}@@"
        idx += 1
        label = html.escape(match.group(1))
        href = html.escape(match.group(2), quote=True)
        tokens[key] = f'<link href="{href}" color="blue">{label}</link>'
        return key

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", link_repl, text)
    text = stash(r"`([^`]+)`", '<font face="Courier">', "</font>", text)
    text = stash(r"\*\*([^*]+)\*\*", "<b>", "</b>", text)
    text = stash(r"\*([^*]+)\*", "<i>", "</i>", text)

    escaped = html.escape(text)

    # Restore placeholders.
    for key, value in tokens.items():
        escaped = escaped.replace(html.escape(key), value)

    return escaped


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}

    styles["paper_header"] = ParagraphStyle(
        "paper_header",
        parent=base["BodyText"],
        fontName="Times-Italic",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=8,
    )

    styles["title"] = ParagraphStyle(
        "title",
        parent=base["Title"],
        fontName="Times-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    styles["author"] = ParagraphStyle(
        "author",
        parent=base["BodyText"],
        fontName="Times-Bold",
        fontSize=12,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    styles["meta"] = ParagraphStyle(
        "meta",
        parent=base["BodyText"],
        fontName="Times-Roman",
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=2,
    )

    styles["abstract_heading"] = ParagraphStyle(
        "abstract_heading",
        parent=base["Heading3"],
        fontName="Times-Bold",
        fontSize=11,
        leading=14,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
    )

    styles["abstract_body"] = ParagraphStyle(
        "abstract_body",
        parent=base["BodyText"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        alignment=TA_JUSTIFY,
        leftIndent=8,
        rightIndent=8,
        spaceAfter=8,
        wordWrap="CJK",
    )

    styles["keywords"] = ParagraphStyle(
        "keywords",
        parent=base["BodyText"],
        fontName="Times-Italic",
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
        leftIndent=8,
        rightIndent=8,
        spaceAfter=14,
        wordWrap="CJK",
    )

    styles["h1"] = ParagraphStyle(
        "h1",
        parent=base["Heading1"],
        fontName="Times-Bold",
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        spaceBefore=14,
        spaceAfter=7,
    )

    styles["h2"] = ParagraphStyle(
        "h2",
        parent=base["Heading2"],
        fontName="Times-Bold",
        fontSize=12,
        leading=15,
        alignment=TA_LEFT,
        spaceBefore=12,
        spaceAfter=5,
    )

    styles["h3"] = ParagraphStyle(
        "h3",
        parent=base["Heading3"],
        fontName="Times-BoldItalic",
        fontSize=11,
        leading=14,
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=4,
    )

    styles["body"] = ParagraphStyle(
        "body",
        parent=base["BodyText"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
        wordWrap="CJK",
    )

    styles["quote"] = ParagraphStyle(
        "quote",
        parent=base["BodyText"],
        fontName="Times-Italic",
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
        leftIndent=22,
        rightIndent=18,
        textColor=colors.HexColor("#2D2D2D"),
        spaceBefore=4,
        spaceAfter=10,
        wordWrap="CJK",
    )

    styles["list"] = ParagraphStyle(
        "list",
        parent=base["BodyText"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        alignment=TA_JUSTIFY,
        leftIndent=16,
        firstLineIndent=-10,
        spaceAfter=5,
        wordWrap="CJK",
    )

    styles["figure_caption"] = ParagraphStyle(
        "figure_caption",
        parent=base["BodyText"],
        fontName="Times-Italic",
        fontSize=9.8,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1F1F1F"),
        spaceBefore=0,
        spaceAfter=8,
        wordWrap="CJK",
    )

    styles["reference"] = ParagraphStyle(
        "reference",
        parent=base["BodyText"],
        fontName="Times-Roman",
        fontSize=9.8,
        leading=13,
        alignment=TA_LEFT,
        leftIndent=14,
        firstLineIndent=-14,
        spaceAfter=5,
        wordWrap="CJK",
    )

    return styles


def add_front_matter(story: list, title: str, author: str, abstract: str, styles: dict[str, ParagraphStyle]) -> None:
    today = dt.date.today().strftime("%B %d, %Y")

    story.append(Paragraph("Technical White Paper | Healthcare Data Reliability Infrastructure", styles["paper_header"]))
    story.append(Paragraph(markdown_inline_to_rml(title), styles["title"]))
    story.append(Paragraph(markdown_inline_to_rml(author), styles["author"]))
    story.append(Paragraph("Interoperability, Encounter Integrity, and Value-Based Operations", styles["meta"]))
    story.append(Paragraph(today, styles["meta"]))
    story.append(Spacer(1, 0.09 * inch))

    divider = Table([[""]], colWidths=[6.5 * inch], rowHeights=[0.02 * inch])
    divider.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#A9A9A9")),
                ("BOX", (0, 0), (-1, -1), 0, colors.white),
            ]
        )
    )
    story.append(divider)
    story.append(Spacer(1, 0.08 * inch))

    story.append(Paragraph("Abstract", styles["abstract_heading"]))
    if abstract:
        story.append(Paragraph(markdown_inline_to_rml(abstract), styles["abstract_body"]))

    keywords = (
        "Keywords: ADT (Admit-Discharge-Transfer), encounter reconciliation, "
        "facility normalization, healthcare data quality, claims integration, "
        "authorization interoperability, value-based care operations"
    )
    story.append(Paragraph(markdown_inline_to_rml(keywords), styles["keywords"]))
    story.append(PageBreak())


def add_figure_placeholder(story: list, text: str, styles: dict[str, ParagraphStyle], page_width: float) -> None:
    fig_text = markdown_inline_to_rml(text)
    inner = Table(
        [[Paragraph(fig_text, styles["figure_caption"])]],
        colWidths=[page_width - 0.25 * inch],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F5F5")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#9A9A9A")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(inner)
    story.append(Spacer(1, 0.04 * inch))


def parse_table(lines: Sequence[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def add_markdown_table(
    story: list,
    rows: list[list[str]],
    styles: dict[str, ParagraphStyle],
    page_width: float,
) -> None:
    if not rows:
        return

    col_count = max(len(row) for row in rows)
    normalized: list[list[Paragraph]] = []
    for row in rows:
        row_cells = row + [""] * (col_count - len(row))
        normalized.append([Paragraph(markdown_inline_to_rml(cell), styles["body"]) for cell in row_cells])

    col_widths = [page_width / col_count] * col_count
    table = Table(normalized, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#A7A7A7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.08 * inch))


def add_body(
    story: list,
    body_lines: Sequence[str],
    styles: dict[str, ParagraphStyle],
    page_width: float,
    skip_exec_summary: bool,
) -> None:
    paragraph_buffer: List[str] = []
    in_references = False
    skipping_exec = False

    def flush_paragraph() -> None:
        if not paragraph_buffer:
            return
        text = " ".join(part.strip() for part in paragraph_buffer if part.strip())
        if text:
            style = styles["reference"] if in_references else styles["body"]
            story.append(Paragraph(markdown_inline_to_rml(text), style))
        paragraph_buffer.clear()

    i = 0
    total = len(body_lines)
    while i < total:
        raw = body_lines[i]
        line = raw.strip()

        if not line:
            flush_paragraph()
            i += 1
            continue

        if line in {"---", "***"}:
            flush_paragraph()
            i += 1
            continue

        heading_match = re.match(r"^(#{2,6})\s+(.*)$", line)
        if heading_match:
            flush_paragraph()
            heading_text = heading_match.group(2).strip()

            if skip_exec_summary and re.match(r"^1\.\s+Executive Summary", heading_text):
                skipping_exec = True
                i += 1
                continue

            if skipping_exec and heading_match.group(1) == "##":
                skipping_exec = False

            if skipping_exec:
                i += 1
                continue

            level = len(heading_match.group(1))
            if level == 2:
                style = styles["h1"]
            elif level == 3:
                style = styles["h2"]
            else:
                style = styles["h3"]

            if re.match(r"^9\.\s+References", heading_text):
                in_references = True

            story.append(Paragraph(markdown_inline_to_rml(heading_text), style))
            i += 1
            continue

        if skipping_exec:
            i += 1
            continue

        if line.startswith("[FIGURE ") or line.startswith("> **Figure"):
            flush_paragraph()
            figure_text = line[2:].strip() if line.startswith("> ") else line
            add_figure_placeholder(story, figure_text, styles, page_width)
            i += 1
            continue

        if line.startswith("> "):
            flush_paragraph()
            quote_lines: List[str] = []
            while i < total and body_lines[i].strip().startswith("> "):
                quote_lines.append(body_lines[i].strip()[2:].strip())
                i += 1
            story.append(Paragraph(markdown_inline_to_rml(" ".join(quote_lines)), styles["quote"]))
            continue

        if re.match(r"^\s*-\s+", line):
            flush_paragraph()
            while i < total and re.match(r"^\s*-\s+", body_lines[i].strip()):
                item = re.sub(r"^\s*-\s+", "", body_lines[i].strip())
                style = styles["reference"] if in_references else styles["list"]
                story.append(Paragraph("• " + markdown_inline_to_rml(item), style))
                i += 1
            continue

        if re.match(r"^\d+\.\s+", line):
            flush_paragraph()
            while i < total and re.match(r"^\d+\.\s+", body_lines[i].strip()):
                numbered_item = body_lines[i].strip()
                number, rest = numbered_item.split(".", 1)
                style = styles["reference"] if in_references else styles["list"]
                story.append(Paragraph(f"{number}. " + markdown_inline_to_rml(rest.strip()), style))
                i += 1
            continue

        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            raw_table_lines: List[str] = []
            while i < total:
                candidate = body_lines[i].strip()
                if candidate.startswith("|") and candidate.endswith("|"):
                    raw_table_lines.append(candidate)
                    i += 1
                else:
                    break
            rows = parse_table(raw_table_lines)
            add_markdown_table(story, rows, styles, page_width)
            continue

        footnote_match = re.match(r"^\[\^(\d+)\]:\s*(.*)$", line)
        if footnote_match:
            flush_paragraph()
            ref_line = f"[{footnote_match.group(1)}] {footnote_match.group(2)}"
            story.append(Paragraph(markdown_inline_to_rml(ref_line), styles["reference"]))
            i += 1
            continue

        paragraph_buffer.append(raw)
        i += 1

    flush_paragraph()


def render_pdf(input_path: Path, output_path: Path, author: str, skip_exec_summary: bool) -> None:
    text_lines = input_path.read_text(encoding="utf-8").splitlines()
    title, body = split_title_and_body(text_lines)
    abstract = extract_exec_summary(body)

    styles = build_styles()

    left = 0.85 * inch
    right = 0.85 * inch
    top = 0.85 * inch
    bottom = 0.75 * inch
    usable_width = LETTER[0] - left - right

    story: list = []
    add_front_matter(story, title=title, author=author, abstract=abstract, styles=styles)
    add_body(
        story,
        body_lines=body,
        styles=styles,
        page_width=usable_width,
        skip_exec_summary=skip_exec_summary,
    )

    short_title = "Admission Signal Reliability"

    def first_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Roman", 9)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(LETTER[0] / 2.0, 0.47 * inch, f"Page {doc.page}")
        canvas.restoreState()

    def later_pages(canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Italic", 8.8)
        canvas.setFillColor(colors.HexColor("#444444"))
        canvas.drawString(left, LETTER[1] - 0.5 * inch, short_title)
        canvas.drawRightString(LETTER[0] - right, LETTER[1] - 0.5 * inch, author)
        canvas.setStrokeColor(colors.HexColor("#B0B0B0"))
        canvas.setLineWidth(0.5)
        canvas.line(left, LETTER[1] - 0.55 * inch, LETTER[0] - right, LETTER[1] - 0.55 * inch)
        canvas.setFont("Times-Roman", 9)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(LETTER[0] / 2.0, 0.47 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=title,
        author=author,
        subject="Healthcare interoperability, admission signal reliability, and value-based operations",
    )

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render publication-style PDF for ASRE white paper")
    parser.add_argument(
        "--input",
        default="/Users/waleed/Desktop/Projects/asre/docs/white-paper-admission-signal-reliability_codex.md",
        help="Path to markdown input",
    )
    parser.add_argument(
        "--output",
        default="/Users/waleed/Desktop/Projects/asre/docs/white-paper-admission-signal-reliability_codex.pdf",
        help="Path to PDF output",
    )
    parser.add_argument(
        "--author",
        default="Waleed Barakat",
        help="Author name displayed on front matter and PDF metadata",
    )
    parser.add_argument(
        "--keep-executive-summary",
        action="store_true",
        help="Keep section 1 in the body in addition to abstract on front matter",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    render_pdf(
        input_path=input_path,
        output_path=output_path,
        author=args.author,
        skip_exec_summary=not args.keep_executive_summary,
    )


if __name__ == "__main__":
    main()
