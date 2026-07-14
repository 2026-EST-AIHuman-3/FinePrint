"""
inspect_file_chunks.py
--------------------------------
특정 source_file의 청크들을 순서대로 출력해서, 청킹이 실제로 의미 단위로
잘 나뉘었는지 눈으로 확인하는 스크립트.

사용법: python inspect_file_chunks.py "전자상거래 등에서 소비자 보호 지침.txt"
"""

import sys
from ingest_rag import collection


def main():
    if len(sys.argv) < 2:
        print('사용법: python inspect_file_chunks.py "파일명"')
        return

    target_file = sys.argv[1]
    result = collection.get(where={"source_file": target_file})

    if not result["ids"]:
        print(f"'{target_file}' 파일의 청크를 찾을 수 없습니다.")
        return

    # chunk_index 순서대로 정렬
    paired = sorted(
        zip(result["metadatas"], result["documents"]),
        key=lambda x: x[0].get("chunk_index", 0),
    )

    print(f"'{target_file}' 총 {len(paired)}개 청크\n")
    for meta, doc in paired:
        idx = meta.get("chunk_index")
        length = len(doc)
        preview = doc[:120].replace("\n", " ")
        print(f"[{idx}] ({length}자) {preview}...")
        print()


if __name__ == "__main__":
    main()