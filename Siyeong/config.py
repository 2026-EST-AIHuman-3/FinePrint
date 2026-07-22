"""
config.py
--------------------------------
DB/임베딩 관련 공용 설정.
ingest_rag.py와 search_utils.py 양쪽에서 이 값을 import해서 사용하면
임베딩 모델 불일치(벡터 공간이 어긋나는 문제)를 구조적으로 방지할 수 있다.
"""
# import os

# DB_PATH = os.getenv("CHROMA_DB_PATH", "./db")
# COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "RAG_system")
# EMBEDDING_MODEL = os.getenv(
#     "CHROMA_EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2"
# )

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

# 소비자 보호 원천과 수집된 서비스 정책의 위치를 실행 경로와 무관하게 고정한다.
# 배포 환경에서는 환경 변수로 각 위치를 바꿀 수 있다.
DATA_PATH = Path(
    os.getenv("FINEPRINT_DATA_PATH", str(BASE_DIR / "data"))
).expanduser().resolve()
# jhc 최종 수집기가 관리하는 서비스별 약관·정책 원문 위치.
COLLECTED_DATA_PATH = Path(
    os.getenv(
        "FINEPRINT_POLICY_DATA_PATH",
        str(PROJECT_ROOT / "jhc" / "RAG"),
    )
).expanduser().resolve()
DB_PATH = os.getenv("CHROMA_DB_PATH", str(BASE_DIR / "db"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "RAG_system")
EMBEDDING_MODEL = os.getenv(
    "CHROMA_EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2"
)


# --------------------------------
# service_name 한글/영어 별칭 매핑
# --------------------------------
# DB에는 ingest 시점의 폴더명(예: "넷플릭스")이 그대로 저장되는데,
# agent(안민재) 쪽에서 사용자 질문으로부터 뽑아내는 service_name이
# 영어("netflix")나 다른 대소문자("NETFLIX")로 들어올 수 있어 검색 시점에
# 후보를 확장해준다. 대소문자 차이는 normalize_service_key로 흡수하고,
# 언어가 다른 경우(한글 <-> 영어)만 이 테이블에 등록한다.
SERVICE_NAME_ALIASES = {
    "netflix": "넷플릭스",
    "넷플릭스": "netflix",
    "youtube": "유튜브",
    "유튜브": "youtube",
    "kakao": "카카오",
    "카카오": "kakao",
    "coupang": "쿠팡",
    "쿠팡": "coupang",
    "tving": "티빙",
    "티빙": "tving",
    # 서비스가 추가될 때마다 여기 한/영 두 줄만 추가하면 된다.
}


def normalize_service_key(service_name: str) -> str:
    """대소문자 차이를 제거해 별칭 테이블 조회용 키로 변환.
    'Netflix' / 'NETFLIX' / 'netflix' -> 'netflix'로 통일.
    한글은 대소문자가 없으므로 이 함수는 그대로 반환한다."""
    return service_name.lower()


def expand_service_name(service_name: str) -> list[str]:
    """입력된 service_name과 그 별칭(있다면)을 모두 검색 후보로 반환.
    매핑 테이블에 없는 값이면 입력값 그대로 1개짜리 리스트를 반환하므로
    (기존 동작과 동일 - 회귀 없음), 이 함수를 안 쓰던 곳에 추가해도 안전하다."""
    if not service_name:
        return []

    candidates = [service_name]
    normalized = normalize_service_key(service_name)
    alias = SERVICE_NAME_ALIASES.get(normalized)
    if alias and alias not in candidates:
        candidates.append(alias)

    return candidates
