"""DocumentLoader — loads PDF, TXT, and EPUB files into raw text.

Dependencies:
- pypdf (PDF)
- ebooklib + html2text (EPUB, optional)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Loads documents from disk into plain text."""

    SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".epub"}

    def load(self, file_path: str | Path) -> str:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}. Supported: {self.SUPPORTED_EXTENSIONS}")

        if ext == ".pdf":
            return self._load_pdf(path)
        elif ext == ".epub":
            return self._load_epub(path)
        else:
            return path.read_text(encoding="utf-8")

    def _load_pdf(self, path: Path) -> str:
        try:
            from pypdf import PdfReader  # type: ignore[import]
        except ImportError:
            raise ImportError("pypdf is required for PDF loading: pip install pypdf")

        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append(f"[Page {i+1}]\n{text}")

        full_text = "\n\n".join(pages)
        logger.info("Loaded PDF: %s (%d pages, %d chars)", path.name, len(reader.pages), len(full_text))
        return full_text

    def _load_epub(self, path: Path) -> str:
        try:
            import ebooklib  # type: ignore[import]
            from ebooklib import epub
            from html2text import html2text  # type: ignore[import]
        except ImportError:
            raise ImportError("ebooklib and html2text are required for EPUB: pip install ebooklib html2text")

        book = epub.read_epub(str(path))
        chapters = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html = item.get_content().decode("utf-8", errors="ignore")
                chapters.append(html2text(html))

        full_text = "\n\n".join(chapters)
        logger.info("Loaded EPUB: %s (%d chapters, %d chars)", path.name, len(chapters), len(full_text))
        return full_text
