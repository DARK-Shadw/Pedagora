"""Document parsing using Docling for PDF/DOCX and python-pptx for PPTX."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedSection:
    title: str
    level: int
    path: str  # e.g. "Chapter 1 > Section 1.2 > Subsection"
    content: str | None
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ParsedFigure:
    image_bytes: bytes
    page_number: int | None = None
    caption: str | None = None
    figure_type: str = "diagram"


@dataclass
class ParsedDocument:
    sections: list[ParsedSection]
    figures: list[ParsedFigure]
    toc: dict | None = None
    page_count: int | None = None


async def parse_document(file_path: str, file_type: str) -> ParsedDocument:
    """Parse a document and extract sections and figures."""
    if file_type in ("pdf", "docx"):
        return await _parse_with_docling(file_path)
    elif file_type == "pptx":
        return await _parse_pptx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


async def _parse_with_docling(file_path: str) -> ParsedDocument:
    """Parse PDF/DOCX using Docling.

    Strategy: use Docling's markdown export (clean, well-structured) then
    split on markdown headings to produce sections. Extract figures from
    the Docling document model's `pictures` list.
    """
    import asyncio
    import re

    def _sync_parse():
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(file_path)
        doc = result.document

        # --- Extract formulas from document model ---
        # Docling detects formulas but export_to_markdown() emits
        # <!-- formula-not-decoded --> placeholders. We collect the
        # original formula text and inject it back into the markdown.
        formula_originals: list[str] = []
        for item, _level in doc.iterate_items():
            if str(item.label).lower() == "formula":
                orig = getattr(item, "orig", "") or ""
                orig = orig.strip()
                if orig and orig != "-":
                    formula_originals.append(orig)
                else:
                    formula_originals.append("")

        # --- Extract sections from markdown export ---
        md = doc.export_to_markdown()

        # Replace <!-- formula-not-decoded --> placeholders with actual
        # formula text wrapped in $$ delimiters for downstream consumers
        placeholder = "<!-- formula-not-decoded -->"
        fi = 0  # formula index
        while placeholder in md and fi < len(formula_originals):
            formula_text = formula_originals[fi]
            if formula_text:
                replacement = f"\n$$\n{formula_text}\n$$\n"
            else:
                replacement = ""
            md = md.replace(placeholder, replacement, 1)
            fi += 1

        # Also fix glyph[epsilon1] → ε (common Docling OCR artifact)
        md = md.replace("glyph[epsilon1]", "ε")
        md = md.replace("glyph[epsilon]", "ε")

        sections: list[ParsedSection] = []
        current_path_parts: list[str] = []

        # Split markdown on heading lines (# ... ## ... ### ...)
        # Keep the heading with its following content
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(heading_pattern.finditer(md))

        if not matches:
            # No headings found — treat entire document as one section
            content = md.strip()
            if content:
                sections.append(ParsedSection(
                    title="Document",
                    level=1,
                    path="Document",
                    content=content,
                ))
        else:
            # Content before the first heading
            pre_content = md[: matches[0].start()].strip()
            if pre_content:
                sections.append(ParsedSection(
                    title="Introduction",
                    level=1,
                    path="Introduction",
                    content=pre_content,
                ))

            for i, m in enumerate(matches):
                level = len(m.group(1))  # number of '#' chars
                title = m.group(2).strip()

                # Content runs from end of this heading line to start of next heading
                content_start = m.end()
                content_end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
                content = md[content_start:content_end].strip()

                # Build hierarchical path
                current_path_parts = current_path_parts[: level - 1]
                current_path_parts.append(title)

                sections.append(ParsedSection(
                    title=title,
                    level=level,
                    path=" > ".join(current_path_parts),
                    content=content if content else None,
                ))

        # --- Extract figures from Docling's picture items ---
        # Docling detects picture regions with bounding boxes, but does not
        # always embed raster data (e.g. vector graphics in LaTeX PDFs).
        # For pictures with image=None, we use pypdfium2 to render the
        # bounding-box region from the original PDF page.
        figures: list[ParsedFigure] = []
        if hasattr(doc, "pictures") and doc.pictures:
            # Collect pictures that need pypdfium2 rendering
            needs_render: list[tuple] = []  # (pic, page_no, bbox, caption)

            for pic in doc.pictures:
                try:
                    # Page number from provenance
                    page_no = None
                    bbox = None
                    if hasattr(pic, "prov") and pic.prov:
                        page_no = pic.prov[0].page_no
                        bbox = pic.prov[0].bbox

                    # Caption: call caption_text(doc) method
                    caption = None
                    if hasattr(pic, "caption_text") and callable(pic.caption_text):
                        try:
                            caption = pic.caption_text(doc)
                        except Exception:
                            pass
                    if not caption and hasattr(pic, "text") and pic.text:
                        caption = pic.text[:200]

                    # Try Docling's embedded image first
                    img_data = None
                    if hasattr(pic, "image") and pic.image:
                        img_obj = pic.image
                        if hasattr(img_obj, "pil_image") and img_obj.pil_image:
                            import io
                            buf = io.BytesIO()
                            img_obj.pil_image.save(buf, format="PNG")
                            img_data = buf.getvalue()
                        elif isinstance(img_obj, bytes):
                            img_data = img_obj

                    if img_data:
                        figures.append(ParsedFigure(
                            image_bytes=img_data,
                            page_number=page_no,
                            caption=caption,
                        ))
                    elif page_no and bbox:
                        needs_render.append((pic, page_no, bbox, caption))
                except Exception as e:
                    logger.warning(f"Failed to process picture item: {e}")

            # Render missing figures via pypdfium2
            if needs_render:
                try:
                    figures.extend(
                        _render_figures_pypdfium(file_path, needs_render)
                    )
                except Exception as e:
                    logger.warning(f"pypdfium2 figure rendering failed: {e}")

        # --- Page count ---
        page_count = None
        num_pages = getattr(doc, "num_pages", None)
        if callable(num_pages):
            try:
                page_count = num_pages()
            except Exception:
                pass
        elif isinstance(num_pages, int):
            page_count = num_pages
        # Fallback: count from provenance across all text items
        if page_count is None and hasattr(doc, "texts"):
            max_page = 0
            for t in doc.texts:
                if hasattr(t, "prov") and t.prov:
                    for p in t.prov:
                        if hasattr(p, "page_no") and p.page_no and p.page_no > max_page:
                            max_page = p.page_no
            if max_page > 0:
                page_count = max_page

        # --- Build TOC ---
        toc = {
            "sections": [
                {"title": s.title, "level": s.level}
                for s in sections
                if s.level <= 2
            ]
        }

        return ParsedDocument(
            sections=sections,
            figures=figures,
            toc=toc,
            page_count=page_count,
        )

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_parse)


def _render_figures_pypdfium(
    pdf_path: str,
    pictures: list[tuple],  # [(pic, page_no, bbox, caption), ...]
) -> list[ParsedFigure]:
    """Render figure regions from a PDF using pypdfium2.

    Docling provides bounding boxes in BOTTOMLEFT coordinates.
    pypdfium2 renders pages at a given scale, then we crop the bbox region.
    """
    import io
    import pypdfium2 as pdfium

    RENDER_SCALE = 2  # 2x for decent quality without huge memory use

    figures: list[ParsedFigure] = []
    pdf = pdfium.PdfDocument(pdf_path)
    total_pages = len(pdf)

    # Group by page to avoid rendering the same page multiple times
    by_page: dict[int, list[tuple]] = {}
    for item in pictures:
        _, page_no, _, _ = item
        by_page.setdefault(page_no, []).append(item)

    for page_no, page_pics in by_page.items():
        if page_no < 1 or page_no > total_pages:
            continue

        page = pdf[page_no - 1]  # 0-indexed
        page_width = page.get_width()
        page_height = page.get_height()

        # Render full page as PIL image
        bitmap = page.render(scale=RENDER_SCALE)
        pil_page = bitmap.to_pil()
        img_width, img_height = pil_page.size

        for _, _, bbox, caption in page_pics:
            try:
                # Docling bbox: BOTTOMLEFT origin (l, t, r, b) in PDF points
                # Convert to pixel coords in the rendered image
                # PDF Y-axis: 0 at bottom, increases upward
                # PIL Y-axis: 0 at top, increases downward
                scale_x = img_width / page_width
                scale_y = img_height / page_height

                left = bbox.l * scale_x
                right = bbox.r * scale_x
                # Flip Y: PIL top = PDF (page_height - top)
                top = (page_height - bbox.t) * scale_y
                bottom = (page_height - bbox.b) * scale_y

                # Ensure correct ordering
                x0 = max(0, int(min(left, right)))
                y0 = max(0, int(min(top, bottom)))
                x1 = min(img_width, int(max(left, right)))
                y1 = min(img_height, int(max(top, bottom)))

                # Skip tiny regions (likely noise)
                if (x1 - x0) < 40 or (y1 - y0) < 40:
                    continue

                cropped = pil_page.crop((x0, y0, x1, y1))

                buf = io.BytesIO()
                cropped.save(buf, format="PNG", optimize=True)
                img_bytes = buf.getvalue()

                figures.append(ParsedFigure(
                    image_bytes=img_bytes,
                    page_number=page_no,
                    caption=caption,
                ))
            except Exception as e:
                logger.warning(f"Failed to crop figure on page {page_no}: {e}")

    pdf.close()
    logger.info(f"Rendered {len(figures)} figures via pypdfium2")
    return figures


async def _parse_pptx(file_path: str) -> ParsedDocument:
    """Parse PPTX using python-pptx."""
    import asyncio

    def _sync_parse():
        from pptx import Presentation

        prs = Presentation(file_path)
        sections: list[ParsedSection] = []
        figures: list[ParsedFigure] = []

        for slide_num, slide in enumerate(prs.slides, 1):
            slide_title = ""
            slide_content = ""

            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text.strip()
                    if shape.shape_type == 13 or (hasattr(shape, 'is_placeholder') and shape.is_placeholder and shape.placeholder_format.idx == 0):
                        # Title placeholder
                        slide_title = text
                    else:
                        slide_content += text + "\n"

                # Extract images
                if shape.shape_type == 13:  # Picture
                    try:
                        image = shape.image
                        figures.append(ParsedFigure(
                            image_bytes=image.blob,
                            page_number=slide_num,
                            caption=slide_title or f"Slide {slide_num}",
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to extract image from slide {slide_num}: {e}")

            if slide_title or slide_content.strip():
                sections.append(ParsedSection(
                    title=slide_title or f"Slide {slide_num}",
                    level=1,
                    path=f"Slide {slide_num}" + (f" > {slide_title}" if slide_title else ""),
                    content=slide_content.strip() or None,
                    page_start=slide_num,
                    page_end=slide_num,
                ))

        toc = {"sections": [{"title": s.title, "level": 1} for s in sections]}

        return ParsedDocument(
            sections=sections,
            figures=figures,
            toc=toc,
            page_count=len(prs.slides),
        )

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_parse)
