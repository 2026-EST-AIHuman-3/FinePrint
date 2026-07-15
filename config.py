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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(BASE_DIR, "db"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "RAG_system")
EMBEDDING_MODEL = os.getenv(
    "CHROMA_EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2"
)