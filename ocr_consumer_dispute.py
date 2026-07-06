"""
ocr_consumer_dispute.py

현재 폴더의 '소비자분쟁해결기준.pdf'를 OCR한 뒤,
GPT로 표/문단 구조를 마크다운 형태로 정리하여
RAG/guideline/소비자분쟁해결기준.txt 로 저장합니다.
"""

from __future__ import annotations

import os
from pathlib import Path

from pdf2image import convert_from_path
import pytesseract
from openai import OpenAI


PDF_PATH = Path("./소비자분쟁해결기준.pdf")
OUTPUT_DIR = Path("./RAG/guideline")
RAW_OCR_PATH = OUTPUT_DIR / "소비자분쟁해결기준_raw_ocr.txt"
FINAL_TXT_PATH = OUTPUT_DIR / "소비자분쟁해결기준.txt"

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def ocr_pdf(pdf_path: Path) -> str:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    print(f"[INFO] OCR 시작: {pdf_path}")

    images = convert_from_path(
        str(pdf_path),
        dpi=300,
    )

    pages = []

    for index, image in enumerate(images, start=1):
        print(f"[OCR] {index}/{len(images)} page")

        text = pytesseract.image_to_string(
            image,
            lang="kor+eng",
            config="--psm 6",
        )

        pages.append(
            f"\n\n--- PAGE {index} ---\n\n{text.strip()}"
        )

    return "\n".join(pages).strip()


def split_text(text: str, max_chars: int = 12000) -> list[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        start = end

    return chunks


def clean_with_gpt(raw_text: str) -> str:
    client = OpenAI()

    chunks = split_text(raw_text)
    cleaned_chunks = []

    for index, chunk in enumerate(chunks, start=1):
        print(f"[GPT] 마크다운 정리 중: {index}/{len(chunks)}")

        response = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "너는 OCR로 추출된 한국어 행정문서와 표를 정리하는 편집자다. "
                        "내용을 임의로 추가하거나 법적 의미를 바꾸지 말고, "
                        "OCR 오류를 문맥상 명확한 범위에서만 고친다. "
                        "표 형태로 보이는 내용은 가능한 마크다운 표로 복원한다. "
                        "표 복원이 어렵다면 항목형 목록으로 정리한다. "
                        "최종 출력은 RAG 검색에 적합한 마크다운 본문만 작성한다."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "다음 OCR 텍스트를 마크다운 형태로 정리해줘.\n\n"
                        f"{chunk}"
                    ),
                },
            ],
        )

        cleaned_chunks.append(response.output_text.strip())

    return "\n\n".join(cleaned_chunks).strip()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_text = ocr_pdf(PDF_PATH)
    RAW_OCR_PATH.write_text(raw_text, encoding="utf-8")

    print(f"[DONE] Raw OCR 저장: {RAW_OCR_PATH}")

    markdown_text = clean_with_gpt(raw_text)

    final_text = (
        "# 소비자분쟁해결기준\n\n"
        "> OCR 후 GPT로 마크다운 형태로 정리한 문서입니다. "
        "원문 PDF와 대조 검토를 권장합니다.\n\n"
        f"{markdown_text}\n"
    )

    FINAL_TXT_PATH.write_text(final_text, encoding="utf-8")

    print(f"[DONE] 최종 TXT 저장: {FINAL_TXT_PATH}")


if __name__ == "__main__":
    main()