"""
config.py
--------------------------------
DB/임베딩 관련 공용 설정.
ingest_rag.py와 search_utils.py 양쪽에서 이 값을 import해서 써야
임베딩 모델 불일치(벡터 공간이 어긋나는 문제)를 구조적으로 방지할 수 있다.
 
사용법:
    from config import DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL
"""
 
DB_PATH = "./db"
COLLECTION_NAME = "RAG_system"
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"