"""
extract_privacy_guideline.py

텍스트 복사가 가능한 PDF에서 페이지별 텍스트를 추출하고,
간단한 품질 점검 결과를 함께 출력합니다.
"""

from pathlib import Path
import fitz  # PyMuPDF


PDF_PATH = Path("./2026 개인정보 처리방침 작성지침.pdf")
OUTPUT_DIR = Path("./privacy_guideline_extract")
RAW_TEXT_PATH = OUTPUT_DIR / "raw_text_by_page.txt"


def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {PDF_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(PDF_PATH)

    all_pages = []
    suspicious_pages = []

    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()

        all_pages.append(
            f"\n\n--- PAGE {page_index} ---\n\n{text}"
        )

        # 너무 짧게 추출된 페이지는 누락 가능성이 있음
        if len(text) < 100:
            suspicious_pages.append((page_index, len(text), "text too short"))

        # 깨진 문자나 이상한 대체 문자가 있으면 점검 대상
        if "�" in text or "\ufffd" in text:
            suspicious_pages.append((page_index, len(text), "broken character found"))

    RAW_TEXT_PATH.write_text("\n".join(all_pages), encoding="utf-8")

    print(f"[DONE] 추출 완료: {RAW_TEXT_PATH}")
    print(f"[INFO] 전체 페이지 수: {len(doc)}")
    print(f"[INFO] 점검 필요 페이지 수: {len(suspicious_pages)}")

    if suspicious_pages:
        print("\n[CHECK] 점검 필요 페이지")
        for page_no, length, reason in suspicious_pages:
            print(f"- page {page_no}: {length} chars / {reason}")


if __name__ == "__main__":
    main()