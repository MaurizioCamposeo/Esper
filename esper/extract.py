"""Extract plain text from archived files."""

import unicodedata
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TEXT_MIME_TYPES = ("text/plain", "text/markdown")
IMAGE_MIME_TYPES = ("image/jpeg", "image/png")
TextSource = Literal["text", "ocr", "caption"]

class UnsupportedFormatError(Exception):
    """Raised when there is no extractor for a file's MIME type."""


class PDFExtractionError(ValueError):
    """A PDF cannot supply usable digital text without another processing step."""


@dataclass(frozen=True)
class TextSection:
    text: str
    page: int | None = None
    source: TextSource = "text"


@dataclass(frozen=True)
class ExtractedDocument:
    sections: tuple[TextSection, ...]
    page_count: int | None = None
    warning: str | None = None


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def normalize_pdf_block(text: str) -> str:
    """Join lowercase word fragments across line endings within a PDF block."""
    def join(match):
        left, right = match.group(1), match.group(2)
        return left + right if left[-1].islower() and right[0].islower() else match.group(0)

    return re.sub(r"([^\W\d_]{2,})[-\u00ad][ \t]*\n[ \t]*([^\W\d_]{2,})", join, normalize_text(text))


def extract_pdf(path: Path) -> ExtractedDocument:
    """Extract digital text per page, preserving physical one-based page numbers."""
    import pymupdf

    try:
        with pymupdf.open(path) as pdf:
            if not pdf.is_pdf:
                raise PDFExtractionError("Il file non è un PDF valido.")
            if pdf.needs_pass:
                raise PDFExtractionError("PDF protetto da password: importa una copia sbloccata.")
            pages = []
            margins = Counter()
            for page in pdf:
                # MuPDF handles layout-aware dehyphenation where possible;
                # the block normalizer also covers explicit lowercase fragments.
                flags = (pymupdf.TEXTFLAGS_BLOCKS | pymupdf.TEXT_DEHYPHENATE) & ~pymupdf.TEXT_PRESERVE_IMAGES
                blocks = page.get_text("blocks", sort=True, flags=flags)
                text_blocks = [(normalize_pdf_block(b[4]), b[3] <= 50 or b[1] >= page.rect.height - 50)
                               for b in blocks if b[6] == 0]
                pages.append(text_blocks)
                margins.update({text.strip() for text, edge in text_blocks if edge and text.strip()})
            # Only identical margin blocks repeated on most pages are removed.
            repeated = {text for text, count in margins.items() if count >= max(3, (len(pages) + 1) // 2)}
            sections, empty = [], []
            for number, blocks in enumerate(pages, 1):
                text = "\n\n".join(text.strip() for text, edge in blocks
                                   if text.strip() and not (edge and text.strip() in repeated))
                if text.strip():
                    sections.append(TextSection(text, number))
                else:
                    empty.append(number)
            if not sections:
                raise PDFExtractionError("Il PDF non contiene testo estraibile. Potrebbe essere una scansione: serve OCR, non ancora disponibile.")
            warning = None
            if empty:
                numbers = ", ".join(map(str, empty[:20])) + (", …" if len(empty) > 20 else "")
                warning = f"Pagine senza testo estraibile: {numbers}. Ricerca parziale; eventuali scansioni richiedono OCR."
            return ExtractedDocument(tuple(sections), len(pages), warning)
    except PDFExtractionError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise PDFExtractionError(f"Impossibile leggere il PDF: {exc}") from exc


def extract_document(path: Path, mime_type: str) -> ExtractedDocument:
    """Expose source sections to the indexer without losing page boundaries."""
    if mime_type == "application/pdf":
        return extract_pdf(path)
    if mime_type in IMAGE_MIME_TYPES:
        from esper.image_text import ImageExtractionError, describe_image, read_image, transcribe_image

        image = read_image(path)
        sections = []
        warnings = []
        for source, label, extract in (
            ("ocr", "OCR", transcribe_image),
            ("caption", "Descrizione", describe_image),
        ):
            try:
                text = extract(image)
            except (ValueError, RuntimeError, OSError, ImportError) as exc:
                warnings.append(f"{label}: {exc}")
            else:
                if text.strip():
                    sections.append(TextSection(normalize_text(text), source=source))
        if not sections:
            raise ImageExtractionError(" ".join(warnings) or "Nessun contenuto indicizzabile.")
        return ExtractedDocument(tuple(sections), warning=" ".join(warnings) or None)
    if mime_type not in TEXT_MIME_TYPES:
        raise UnsupportedFormatError(mime_type)
    return ExtractedDocument((TextSection(normalize_text(decode_text(path.read_bytes()))),))

def decode_text(data: bytes) -> str:
    """Decode bytes as UTF-8 (with or without BOM), falling back to Windows-1252."""
    try:
        text = data.decode("utf-8-sig") # decode to remove the BOM in order not to let it finish in the first chunk of the embedding process
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace") # cp1252 contains 5 byte not defined, replacing them we can avoid exceptions
    return text 

def extract_text(path: Path, mime_type: str) -> str:
    """Return the text of a file, with normalized newlines and Unicode form."""
    return "\n\n".join(section.text for section in extract_document(path, mime_type).sections)

