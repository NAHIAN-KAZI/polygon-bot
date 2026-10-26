import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader
from docx import Document

from app.config import settings


@dataclass
class PageText:
    page: int | None
    text: str


@dataclass
class Chunk:
    text: str
    chunk_index: int
    page: int | None
    # Set for markdown only: where in the document this chunk sits, so a hit can say which section and
    # product it came from. `product` and `group` are the level-3 and level-2 headings of a page-per-section file.
    section: str | None = None
    heading_path: list[str] = field(default_factory=list)
    source_url: str | None = None
    product: str | None = None
    group: str | None = None


def extract_pages(filename: str, data: bytes) -> list[PageText]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return [PageText(page=i + 1, text=p.extract_text() or "") for i, p in enumerate(reader.pages)]
    if lower.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
        return [PageText(page=None, text=text)]
    # txt / md / anything else: decode as plain text
    return [PageText(page=None, text=data.decode("utf-8", errors="ignore"))]


def _split_recursive(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    for separator in ["\n\n", "\n", ". ", " "]:
        parts = text.split(separator)
        if len(parts) > 1:
            break
    else:
        parts = list(text)
        separator = ""

    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = (current + separator + part) if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(part) > chunk_size:
                chunks.extend(_split_recursive(part, chunk_size, overlap))
                current = ""
            else:
                current = part
    if current:
        chunks.append(current)

    # apply overlap between consecutive chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:]):
            tail = prev[-overlap:] if len(prev) > overlap else prev
            overlapped.append((tail + separator + cur) if separator else (tail + cur))
        chunks = overlapped

    return chunks


def _split_markdown_sections(text: str) -> list[str]:
    sections = re.split(r"(?m)^(?=#{1,6}\s)", text)
    return [s for s in sections if s.strip()] or [text]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SOURCE_RE = re.compile(r"^Source:\s*(\S+)\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")
MIN_CHUNK_CHARS = 80


@dataclass
class _Block:
    path: list[str]
    lines: list[str]
    levels: list[int] = field(default_factory=list)


def _markdown_blocks(text: str) -> tuple[list[_Block], dict[tuple, str]]:
    """Heading-delimited blocks with their heading path, plus each page's `Source:` URL.

    A `Source: <url>` line closes a page (the level-3 section it sits in) and is taken out of the text:
    it becomes metadata, not something to embed. Headings inside a fenced code block are not headings."""
    stack: list[tuple[int, str]] = []
    blocks = [_Block([], [])]
    sources: dict[tuple, str] = {}
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            blocks.append(_Block([t for _, t in stack], [], [lvl for lvl, _ in stack]))
            continue
        source = None if in_fence else _SOURCE_RE.match(line)
        if source and any(lvl == 3 for lvl, _ in stack):
            page_key = tuple(t for lvl, t in stack if lvl <= 3)
            sources[page_key] = source.group(1)
            continue
        blocks[-1].lines.append(line)
    return blocks, sources


def _units(lines: list[str], size: int) -> list[str]:
    """Paragraphs and whole tables. A table too long for one chunk is cut into row groups that each repeat
    the header row, so a data row is never separated from its column names."""
    units: list[str] = []
    paragraph: list[str] = []
    table: list[str] = []

    def flush_paragraph() -> None:
        text = "\n".join(paragraph).strip()
        paragraph.clear()
        if text:
            units.extend(_split_recursive(text, size, 0) if len(text) > size else [text])

    def flush_table() -> None:
        rows = [r for r in table]
        table.clear()
        if not rows:
            return
        has_sep = len(rows) > 1 and _TABLE_SEPARATOR_RE.match(rows[1].strip() or "") is not None
        header = rows[:2] if has_sep else rows[:1]
        body = rows[len(header):]
        whole = "\n".join(rows)
        if len(whole) <= size or not body:
            units.append(whole)
            return
        head_text = "\n".join(header)
        group: list[str] = []
        for row in body:
            if group and len(head_text) + len("\n".join(group)) + len(row) + 2 > size:
                units.append(head_text + "\n" + "\n".join(group))
                group = []
            group.append(row)
        if group:
            units.append(head_text + "\n" + "\n".join(group))

    for line in lines:
        if line.lstrip().startswith("|"):
            flush_paragraph()
            table.append(line.rstrip())
        elif not line.strip():
            flush_table()
            flush_paragraph()
        else:
            flush_table()
            paragraph.append(line.rstrip())
    flush_table()
    flush_paragraph()
    return units


def _pack(units: list[str], size: int) -> list[str]:
    """Fills chunks up to `size` with whole units, then folds any chunk under MIN_CHUNK_CHARS into a neighbour."""
    chunks: list[str] = []
    current = ""
    for unit in units:
        joined = (current + "\n\n" + unit) if current else unit
        if len(joined) <= size or not current:
            current = joined
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(chunk) < MIN_CHUNK_CHARS and len(merged[-1]) + len(chunk) + 2 <= size * 1.25:
            merged[-1] = merged[-1] + "\n\n" + chunk
        else:
            merged.append(chunk)
    if len(merged) > 1 and len(merged[0]) < MIN_CHUNK_CHARS and len(merged[0]) + len(merged[1]) + 2 <= size * 1.25:
        merged[1] = merged[0] + "\n\n" + merged[1]
        merged = merged[1:]
    return merged


def _chunk_markdown(text: str, page: int | None, start_index: int) -> list[Chunk]:
    blocks, sources = _markdown_blocks(text)
    chunks: list[Chunk] = []
    idx = start_index
    for block in blocks:
        if not any(line.strip() for line in block.lines):
            continue
        by_level = dict(zip(block.levels, block.path))
        product = by_level.get(3)          # a page of a page-per-section file
        group = by_level.get(2) if product else None
        page_key = tuple(t for lvl, t in zip(block.levels, block.path) if lvl <= 3)
        # The document title (level 1) is the same on every chunk, so it is left out of the visible prefix.
        shown = [t for lvl, t in zip(block.levels, block.path) if lvl > 1] or block.path
        prefix = f"[{' > '.join(shown)}]\n" if shown else ""
        for body in _pack(_units(block.lines, settings.CHUNK_SIZE), settings.CHUNK_SIZE):
            chunks.append(Chunk(
                text=prefix + body, chunk_index=idx, page=page,
                section=block.path[-1] if block.path else None, heading_path=list(block.path),
                source_url=sources.get(page_key) if product else None, product=product, group=group))
            idx += 1
    return chunks


def chunk_document(filename: str, data: bytes) -> list[Chunk]:
    pages = extract_pages(filename, data)
    chunks: list[Chunk] = []
    idx = 0

    is_markdown = filename.lower().endswith(".md")

    for page in pages:
        if is_markdown:
            md_chunks = _chunk_markdown(page.text, page.page, idx)
            chunks.extend(md_chunks)
            idx += len(md_chunks)
            continue
        for section in [page.text]:
            for piece in _split_recursive(section, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP):
                if piece.strip():
                    chunks.append(Chunk(text=piece, chunk_index=idx, page=page.page))
                    idx += 1

    return chunks
