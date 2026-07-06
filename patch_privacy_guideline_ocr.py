"""
patch_privacy_guideline_ocr.py

PyMuPDF로 추출한 raw_text_by_page.txt를 기반으로,
텍스트가 짧게 추출된 페이지만 OCR 보완한 뒤
merged_text_by_page.txt를 생성합니다.
"""

from pathlib import Path
import re

import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path


PDF_PATH = Path("./2026 개인정보 처리방침 작성지침.pdf")
RAW_TEXT_PATH = Path("./privacy_guideline_extract/raw_text_by_page.txt")
OUTPUT_PATH = Path("./privacy_guideline_extract/merged_text_by_page.txt")

SUSPICIOUS_PAGES = [
    1, 2, 3, 5, 8, 9, 13, 21, 46, 88, 89, 104, 109, 118, 119,
    140, 141, 142, 162, 168, 171, 175, 178, 179, 184, 185,
]


def extract_pages_from_raw(raw_text: str) -> dict[int, str]:
    pattern = re.compile(
        r"--- PAGE (\d+) ---\n\n(.*?)(?=\n\n--- PAGE \d+ ---|\Z)",
        re.DOTALL,
    )

    pages = {}

    for match in pattern.finditer(raw_text):
        page_no = int(match.group(1))
        text = match.group(2).strip()
        pages[page_no] = text

    return pages


def ocr_page(pdf_path: Path, page_no: int) -> str:
    images = convert_from_path(
        str(pdf_path),
        dpi=300,
        first_page=page_no,
        last_page=page_no,
    )

    if not images:
        return ""

    image = images[0]

    text = pytesseract.image_to_string(
        image,
        lang="kor+eng",
        config="--psm 6",
    )

    return text.strip()


def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {PDF_PATH}")

    if not RAW_TEXT_PATH.exists():
        raise FileNotFoundError(f"raw_text_by_page.txt 파일을 찾을 수 없습니다: {RAW_TEXT_PATH}")

    raw_text = RAW_TEXT_PATH.read_text(encoding="utf-8")
    pages = extract_pages_from_raw(raw_text)

    doc = fitz.open(PDF_PATH)
    total_pages = len(doc)

    for page_no in SUSPICIOUS_PAGES:
        print(f"[OCR] page {page_no}/{total_pages}")

        original_text = pages.get(page_no, "").strip()
        ocr_text = ocr_page(PDF_PATH, page_no)

        if not ocr_text:
            print(f"[SKIP] page {page_no}: OCR 결과 없음")
            continue

        # OCR 결과가 기존 텍스트보다 충분히 길면 대체
        if len(ocr_text) > len(original_text) + 50:
            pages[page_no] = (
                f"{ocr_text}\n\n"
                f"[NOTE] 이 페이지는 OCR로 보완되었습니다."
            )
            print(
                f"[PATCH] page {page_no}: "
                f"{len(original_text)} chars -> {len(ocr_text)} chars"
            )
        else:
            print(
                f"[KEEP] page {page_no}: "
                f"기존 {len(original_text)} chars / OCR {len(ocr_text)} chars"
            )

    merged = []

    for page_no in range(1, total_pages + 1):
        merged.append(
            f"\n\n--- PAGE {page_no} ---\n\n{pages.get(page_no, '').strip()}"
        )

    OUTPUT_PATH.write_text("\n".join(merged).strip(), encoding="utf-8")

    print(f"\n[DONE] 병합 파일 저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()