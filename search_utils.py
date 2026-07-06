"""
search_utils.py
--------------------------------
Retrieval helpers for the RAG/Agent layer.

This file assumes ingest_rag.py has already created/upserted ChromaDB data.
"""

from __future__ import annotations

import chromadb
from chromadb.utils import embedding_functions


DB_PATH = "./db"
COLLECTION_NAME = "RAG_system"
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"

DOMAIN_KEYWORDS = [
    "청약철회",
    "청약 철회",
    "환불",
    "해지",
    "위약금",
    "자동결제",
    "자동갱신",
    "개인정보",
    "제3자 제공",
    "손해배상",
    "대금환급",
]


def get_collection(
    db_path: str = DB_PATH,
    collection_name: str = COLLECTION_NAME,
):
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
    )


collection = get_collection()


def normalize_text(text: str) -> str:
    return text.replace(" ", "")


def extract_keywords_in_query(query: str) -> list[str]:
    normalized_query = normalize_text(query)
    return [
        keyword
        for keyword in DOMAIN_KEYWORDS
        if normalize_text(keyword) in normalized_query
    ]


def build_where_filter(doc_type: str | list[str] | None = None) -> dict | None:
    if doc_type is None:
        return None

    if isinstance(doc_type, str):
        return {"type": doc_type}

    if len(doc_type) == 1:
        return {"type": doc_type[0]}

    return {"type": {"$in": doc_type}}


def hybrid_search(
    query: str,
    n_results: int = 3,
    candidate_pool: int = 15,
    doc_type: str | list[str] | None = None,
) -> list[dict]:
    count = collection.count()
    if count == 0:
        print("[ERROR] DB is empty. Run ingest_rag.py first.")
        return []

    keywords = extract_keywords_in_query(query)
    where = build_where_filter(doc_type)

    query_kwargs = {
        "query_texts": [query],
        "n_results": min(candidate_pool, count),
    }
    if where:
        query_kwargs["where"] = where

    raw = collection.query(**query_kwargs)

    docs = raw["documents"][0]
    metas = raw["metadatas"][0]
    distances = raw["distances"][0]
    ids = raw["ids"][0]

    reranked = []
    for doc_id, doc, meta, distance in zip(ids, docs, metas, distances):
        normalized_doc = normalize_text(doc)
        matched = sum(
            1 for keyword in keywords if normalize_text(keyword) in normalized_doc
        )
        adjusted_score = distance - (matched * 0.15)
        reranked.append(
            {
                "id": doc_id,
                "text": doc,
                "metadata": meta,
                "distance": distance,
                "keyword_match": matched,
                "score": adjusted_score,
            }
        )

    reranked.sort(key=lambda item: item["score"])
    return reranked[:n_results]


def search_law_and_guideline(
    query: str,
    n_results: int = 3,
    candidate_pool: int = 15,
) -> list[dict]:
    return hybrid_search(
        query=query,
        n_results=n_results,
        candidate_pool=candidate_pool,
        doc_type=["law", "guideline"],
    )


def print_results(results: list[dict], preview_chars: int = 250) -> None:
    for index, result in enumerate(results, start=1):
        metadata = result["metadata"]
        print(f"\n[{index}]")
        print("TEXT:", result["text"][:preview_chars])
        print("TYPE:", metadata.get("type"))
        print("ARTICLE:", metadata.get("article", "unknown"))
        print("SOURCE:", metadata.get("source"))
        print(
            f"DISTANCE: {result['distance']:.4f} / "
            f"KEYWORD_MATCH: {result['keyword_match']} / "
            f"SCORE: {result['score']:.4f}"
        )


if __name__ == "__main__":
    sample_queries = [
        "제3자에게 개인정보를 제공하나요?",
        "디지털콘텐츠도 청약철회가 되나요?",
    ]

    for sample_query in sample_queries:
        print("\n======================")
        print(f"QUERY: {sample_query}")
        print("======================")
        print_results(search_law_and_guideline(sample_query))
