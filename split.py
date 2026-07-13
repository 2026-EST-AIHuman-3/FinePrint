"""
split_privacy_guideline.py
--------------------------------
merged_text_by_page.txt (OCR로 병합된 페이지별 텍스트)를
문서의 실제 목차 구조(Part Ⅰ~Ⅴ, 부록 1~9) 기준으로 자동 분리한다.

[사용된 구분 기준]
1. 본문 5개 대장(Part)은 각 페이지 상단에 반복되는 러닝헤더로 구분됨:
   "Part Ⅰ. 개요", "Part Ⅱ. 개인정보 처리방침 작성 기본사항",
   "Part Ⅲ. 개인정보 처리방침 작성 방법", "Part Ⅳ. 개인정보 처리방침 공개 방법",
   "Part Ⅴ. 주요 개인정보 처리 표시(라벨링) 방법"

2. 부록은 전체를 하나의 장으로 보지 않고, 실제로 9개의 독립된 가이드
   모음이라 각 항목 제목(예: "부록 1 생성형 인공지능(AI) 서비스 처리방침 부록")
   을 기준으로 다시 9개로 세분화함.

3. 첫 Part 헤더가 나오기 전(표지, 목차, 발간사 등)은 별도 파일(00_표지_목차)로 저장.

[출력]
RAG/guideline/개인정보처리방침작성지침_2026/
    00_표지_목차.txt
    01_Part1_개요.txt
    02_Part2_개인정보_처리방침_작성_기본사항.txt
    03_Part3_개인정보_처리방침_작성_방법.txt
    04_Part4_개인정보_처리방침_공개_방법.txt
    05_Part5_주요_개인정보_처리_표시(라벨링)_방법.txt
    06_부록1_생성형_인공지능(AI)_서비스_처리방침_부록.txt
    07_부록2_아동을_위한_개인정보_처리방침_작성방안_및_예시.txt
    ... (부록 9까지)
"""

import re
from pathlib import Path

INPUT_FILE = "privacy_guideline_extract/merged_text_by_page.txt"
OUTPUT_DIR = Path("RAG/guideline/개인정보처리방침작성지침_2026")

# 본문 5개 대장 러닝헤더 (등장 순서 그대로, 페이지마다 반복되므로 "처음 등장 지점"만 경계로 사용)
PART_PATTERN = re.compile(
    r"^Part\s*([ⅠⅡⅢⅣⅤ])\.\s*(\S.+?)\s+\d+\s*$",
    re.MULTILINE
)

# 부록 항목 제목 (부록 N 제목) - 줄바꿈까지 흡수하지 않도록 [ \t]+ 로 제한
APPENDIX_ITEM_PATTERN = re.compile(
    r"^부록\s*([0-9]+)[ \t]+(\S.+)$",
    re.MULTILINE
)

PART_ORDER = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"]


def safe_filename(text: str, max_len: int = 40) -> str:
    """파일명에 쓸 수 없는 문자 제거 및 길이 제한"""
    text = re.sub(r"[\\/:*?\"<>|]", "", text)
    text = text.strip().replace(" ", "_")
    return text[:max_len]


def find_boundaries(text: str):
    """
    Part 헤더와 부록 항목 헤더의 '첫 등장 위치'만 골라서
    (위치, 종류, 라벨, 제목) 리스트로 정리.
    같은 Part/부록 헤더가 페이지마다 반복되므로, 각 라벨이
    처음 나타난 지점만 실제 "장 시작점"으로 취급한다.
    """
    boundaries = []
    seen_parts = set()
    seen_appendix = set()

    for m in PART_PATTERN.finditer(text):
        roman = m.group(1)
        title = m.group(2).strip()
        if roman not in seen_parts:
            seen_parts.add(roman)
            boundaries.append((m.start(), "part", roman, title))

    for m in APPENDIX_ITEM_PATTERN.finditer(text):
        num = m.group(1)
        title = m.group(2).strip()
        if num not in seen_appendix:
            seen_appendix.add(num)
            boundaries.append((m.start(), "appendix", num, title))

    boundaries.sort(key=lambda x: x[0])
    return boundaries


def split_sections(text: str):
    """경계 지점 기준으로 텍스트를 섹션별로 자름"""
    boundaries = find_boundaries(text)

    if not boundaries:
        print("[WARNING] Part/부록 헤더를 하나도 찾지 못했습니다. "
              "패턴을 다시 확인하세요.")
        return []

    sections = []

    # 첫 경계 이전 = 표지/목차/발간사 등
    front_matter = text[: boundaries[0][0]].strip()
    if front_matter:
        sections.append({
            "index": 0,
            "kind": "front",
            "label": "표지_목차",
            "title": "표지 및 목차",
            "content": front_matter,
        })

    for i, (pos, kind, label, title) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        content = text[pos:end].strip()
        sections.append({
            "index": i + 1,
            "kind": kind,
            "label": label,
            "title": title,
            "content": content,
        })

    return sections


def build_filename(section: dict) -> str:
    idx = section["index"]

    if section["kind"] == "front":
        return f"00_{section['label']}.txt"

    if section["kind"] == "part":
        part_no = PART_ORDER.index(section["label"]) + 1
        title = safe_filename(section["title"])
        return f"{idx:02d}_Part{part_no}_{title}.txt"

    if section["kind"] == "appendix":
        title = safe_filename(section["title"])
        return f"{idx:02d}_부록{section['label']}_{title}.txt"

    return f"{idx:02d}_섹션.txt"


def main():
    input_path = Path(INPUT_FILE)
    if not input_path.exists():
        print(f"[ERROR] 입력 파일이 없습니다: {input_path}")
        return

    text = input_path.read_text(encoding="utf-8")

    sections = split_sections(text)
    if not sections:
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for section in sections:
        filename = build_filename(section)
        out_path = OUTPUT_DIR / filename
        out_path.write_text(section["content"], encoding="utf-8")
        print(f"[DONE] {filename}  ({len(section['content'])}자)")

    print(f"\n[SUMMARY] 총 {len(sections)}개 섹션 생성 완료 -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()