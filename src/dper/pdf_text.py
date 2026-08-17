from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .utils import sha256_file

try:
    import pdfplumber
except Exception:  # pragma: no cover - optional dependency fallback
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency fallback
    PdfReader = None


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class ReportInput:
    report_id: str
    path: Path
    sha256: str
    duplicate_count: int = 1


@dataclass(frozen=True)
class ExtractedReport:
    report: ReportInput
    pages: list[PageText]
    extraction_status: str

    @property
    def text_chars(self) -> int:
        return sum(len(page.text) for page in self.pages)


def iter_pdf_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(path for path in input_path.rglob("*") if path.suffix.lower() == ".pdf")


def read_reports(input_path: Path) -> list[ReportInput]:
    groups: dict[str, list[Path]] = {}
    for pdf in iter_pdf_paths(input_path):
        groups.setdefault(sha256_file(pdf), []).append(pdf)

    reports: list[ReportInput] = []
    for digest, paths in sorted(groups.items(), key=lambda item: str(min(item[1])).lower()):
        canonical = min(paths, key=lambda path: (path.name.lower().count("copy of"), len(path.name), path.name.lower()))
        reports.append(ReportInput(report_id=f"N{digest[:12]}", path=canonical, sha256=digest, duplicate_count=len(paths)))
    return reports


def extract_pdf_text(report: ReportInput) -> ExtractedReport:
    pages: list[PageText] = []
    status = "text_extracted"
    if pdfplumber is not None:
        try:
            with pdfplumber.open(str(report.path)) as pdf:
                for idx, page in enumerate(pdf.pages, 1):
                    try:
                        text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    except Exception:
                        text = ""
                    pages.append(PageText(idx, text))
        except Exception as exc:
            status = f"pdfplumber_error:{exc.__class__.__name__}"

    if not pages and PdfReader is not None:
        try:
            reader = PdfReader(str(report.path))
            for idx, page in enumerate(reader.pages, 1):
                pages.append(PageText(idx, page.extract_text() or ""))
            status = "text_extracted_pypdf"
        except Exception as exc:
            status = f"pypdf_error:{exc.__class__.__name__}"

    if not pages:
        pages = [PageText(1, "")]
    if sum(len(page.text.strip()) for page in pages) < 100:
        status = "ocr_needed_or_sparse_text"
    return ExtractedReport(report=report, pages=pages, extraction_status=status)


def chunk_pages(pages: list[PageText], max_chars: int) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    current: list[str] = []
    start_page = pages[0].page_number if pages else 1
    end_page = start_page
    current_len = 0

    for page in pages:
        page_text = f"\n\n=== PAGE {page.page_number} ===\n{page.text.strip()}"
        if current and current_len + len(page_text) > max_chars:
            chunks.append((start_page, end_page, "".join(current).strip()))
            current = []
            current_len = 0
            start_page = page.page_number
        current.append(page_text)
        current_len += len(page_text)
        end_page = page.page_number

    if current:
        chunks.append((start_page, end_page, "".join(current).strip()))
    return chunks or [(1, 1, "")]
