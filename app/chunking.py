import io
import re
from dataclasses import dataclass

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


def chunk_document(filename: str, data: bytes) -> list[Chunk]:
    pages = extract_pages(filename, data)
    chunks: list[Chunk] = []
    idx = 0

    is_markdown = filename.lower().endswith(".md")

    for page in pages:
        sections = _split_markdown_sections(page.text) if is_markdown else [page.text]
        for section in sections:
            for piece in _split_recursive(section, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP):
                if piece.strip():
                    chunks.append(Chunk(text=piece, chunk_index=idx, page=page.page))
                    idx += 1

    return chunks
