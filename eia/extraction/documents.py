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


# What makes a page worth reading in a long annual report (weights). Financial statements usually sit in the
# second half of a 300-700 page report, so a plain "first N pages" cut misses them.
PAGE_SIGNALS = [
    (re.compile(r"consolidated\s+(balance\s+sheet|statement\s+of\s+profit|statement\s+of\s+cash|cash\s+flow)", re.I), 6),
    (re.compile(r"statement\s+of\s+profit\s+and\s+loss|balance\s+sheet\s+as\s+at|cash\s+flow\s+statement", re.I), 4),
    (re.compile(r"(ten|10|five|5)[\s-]+year|financial\s+highlights|key\s+(financial|performance|operational)|"
                r"at\s+a\s+glance|performance\s+highlights|operational\s+highlights", re.I), 5),
    (re.compile(r"installed\s+capacity|commissioned|generation|production|throughput|offtake|transmission\s+(lines|network)|"
                r"capacity\s+addition|plant\s+load\s+factor|\bPLF\b|\bCUF\b", re.I), 2),
    (re.compile(r"borrowings|finance\s+costs|trade\s+receivables|capital\s+expenditure|\bcapex\b|revenue\s+from\s+operations", re.I), 2),
    (re.compile(r"\btarget|by\s+(FY\s?)?20[3-5]\d|\bguidance\b", re.I), 1),
]


def choose_pages(pdf, max_pages: int) -> list[int]:
    """Page indexes to read: all of them if within budget; else the opening pages plus the highest-scoring rest."""
    n = len(pdf)
    if n <= max_pages:
        return list(range(n))
    head = min(max_pages // 3, 100)
    scores = []
    for i in range(head, n):
        try:
            t = pdf[i].get_text("text")[:6000]
        except Exception:
            t = ""
        sc = sum(w * min(3, len(rx.findall(t))) for rx, w in PAGE_SIGNALS) if t.strip() else 0
        scores.append((sc, i))
    budget = max_pages - head
    best = [i for sc, i in sorted(scores, key=lambda x: (-x[0], x[1])) if sc > 0][:budget]
    if len(best) < budget:  # fill the rest in reading order
        rest = [i for _, i in scores if i not in set(best)]
        best += rest[:budget - len(best)]
    return sorted(set(range(head)) | set(best))


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
                chosen = choose_pages(pdf, max_pages)
                if len(chosen) < len(pdf):
                    doc.warnings.append(f"Read {len(chosen)} of {len(pdf)} pages: the opening pages plus the pages "
                                        "holding financial statements, multi-year highlights and operating data.")
                for i in chosen:
                    words = pdf[i].get_text("words")
                    doc.pages.append(Page(i + 1, _rows_from_words(words) if words else ""))
            doc.parser = "pymupdf"
            if any(p.text.strip() for p in doc.pages):
                return doc
            # no text at all: some PDFs defeat one reader and not another; try a second one on the opening pages
            doc.warnings.append("PyMuPDF found no text; trying a second PDF reader on the first pages.")
            doc.pages = []
            max_pages = min(max_pages, 40)
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
