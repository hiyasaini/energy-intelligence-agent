"""Turn fetched bytes into page-numbered text.

PDF: PyMuPDF (preferred). Words are regrouped into visual rows so financial tables keep their
row/column shape. If PyMuPDF is unavailable, pdfplumber, then pypdf, are used as fallbacks.
HTML: BeautifulSoup text with block structure preserved. Plain text: split on form-feeds.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - depends on environment
    fitz = None


@dataclass
class Page:
    number: int          # 1-based physical page number in the source
    text: str


@dataclass
class Document:
    pages: list[Page] = field(default_factory=list)
    title: str = ""
    kind: str = "text"   # pdf | html | text
    parser: str = ""
    published_hint: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)


def _rows_from_words(words: list, y_tol: float = 3.0) -> str:
    """words: (x0, y0, x1, y1, text, ...) -> lines ordered top-to-bottom, left-to-right."""
    rows: list[list] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if rows and abs(rows[-1][0] - yc) <= y_tol:
            rows[-1][1].append(w)
        else:
            rows.append([yc, [w]])
    lines = []
    for _, ws in rows:
        ws.sort(key=lambda w: w[0])
        parts, prev_x1 = [], None
        for w in ws:
            gap = (w[0] - prev_x1) if prev_x1 is not None else 0
            parts.append(("   " if gap > 8 else " ") + w[4] if parts else w[4])
            prev_x1 = w[2]
        lines.append("".join(parts))
    return "\n".join(lines)


def parse_pdf(data: bytes, max_pages: int = 60) -> Document:
    doc = Document(kind="pdf")
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as pdf:
                doc.title = (pdf.metadata or {}).get("title", "") or ""
                cd = (pdf.metadata or {}).get("creationDate", "") or ""
                m = re.match(r"D:(\d{4})(\d{2})(\d{2})", cd)
                if m:
                    doc.published_hint = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                n = min(len(pdf), max_pages)
                if len(pdf) > max_pages:
                    doc.warnings.append(f"Only first {max_pages} of {len(pdf)} pages parsed.")
                for i in range(n):
                    words = pdf[i].get_text("words")
                    doc.pages.append(Page(i + 1, _rows_from_words(words) if words else ""))
            doc.parser = "pymupdf"
            return doc
        except Exception as e:  # fall through to alternatives
            doc.warnings.append(f"PyMuPDF failed: {e}")
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            n = min(len(pdf.pages), max_pages)
            if len(pdf.pages) > max_pages:
                doc.warnings.append(f"Only first {max_pages} of {len(pdf.pages)} pages parsed.")
            for i in range(n):
                doc.pages.append(Page(i + 1, pdf.pages[i].extract_text() or ""))
        doc.parser = "pdfplumber"
        return doc
    except Exception as e:
        doc.warnings.append(f"pdfplumber failed: {e}")
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        for i, p in enumerate(r.pages[:max_pages]):
            doc.pages.append(Page(i + 1, p.extract_text() or ""))
        doc.parser = "pypdf"
    except Exception as e:
        doc.warnings.append(f"pypdf failed: {e}")
    return doc


def parse_html(data: bytes | str) -> Document:
    from bs4 import BeautifulSoup
    html = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    soup = BeautifulSoup(html, "lxml") if _has_lxml() else BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "form"]):
        t.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    # table rows -> one line per row, cells separated by wide gaps (keeps table shape)
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        tr.replace_with(soup.new_string("\n" + "   ".join(cells) + "\n"))
    text = soup.get_text("\n")
    text = re.sub(r"\n\s*\n+", "\n", text)
    pub = None
    meta = soup.find("meta", attrs={"property": "article:published_time"}) or \
        soup.find("meta", attrs={"name": re.compile("date|publish", re.I)})
    if meta and meta.get("content"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", meta["content"])
        pub = m.group(1) if m else None
    return Document(pages=[Page(1, text)], title=title, kind="html", parser="bs4", published_hint=pub)


_PAGE_MARK = re.compile(r"^\s*\[\[page\s+(\d+)\]\]\s*$", re.I | re.M)


def parse_text(text: str, title: str = "") -> Document:
    """Plain text; form-feeds separate pages. A '[[page N]]' line sets the printed page number of that chunk
    (used for transcribed excerpts so citations keep the original page)."""
    chunks = text.split("\f") if "\f" in text else [text]
    pages = []
    for i, c in enumerate(chunks):
        m = _PAGE_MARK.search(c)
        n = int(m.group(1)) if m else i + 1
        pages.append(Page(n, _PAGE_MARK.sub("", c) if m else c))
    if not title:
        first = next((l.strip() for l in text.splitlines() if l.strip()), "")
        title = first[:150]
    return Document(pages=pages, title=title, kind="text", parser="text")


def parse_bytes(data: bytes, content_type: str = "", url: str = "", max_pages: int = 60) -> Document:
    ct = (content_type or "").lower()
    if data[:4] == b"PK\x03\x04":  # NSE sometimes files annual reports as zip archives
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                pdfs = sorted((i for i in z.infolist() if i.filename.lower().endswith(".pdf")), key=lambda i: -i.file_size)
                if pdfs:
                    doc = parse_pdf(z.read(pdfs[0]), max_pages)
                    doc.warnings.append(f"Read {pdfs[0].filename} from a zip archive.")
                    return doc
        except zipfile.BadZipFile:
            pass
    head = data[:1024].lstrip(b"\xef\xbb\xbf \r\n\t")
    if head[:5] == b"%PDF-":  # decide by content, never by URL or declared type alone
        return parse_pdf(data, max_pages)
    if "html" in ct or re.search(rb"<\s*html|<\s*body|<\s*div", data[:4000], re.I):
        return parse_html(data)
    return parse_text(data.decode("utf-8", "ignore"))


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except Exception:
        return False
