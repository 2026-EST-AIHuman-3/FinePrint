import chromadb
from chromadb.config import Settings

# 1. DB 생성
client = chromadb.PersistentClient(path="./db")

collection = client.get_or_create_collection(
    name="legal_docs"
)

# 2. 테스트 데이터 (PDF 대신 먼저 문자열로 테스트)
texts = [
    "전자상거래법은 소비자 보호를 위한 법이다.",
    "청약 철회는 7일 이내 가능하다.",
    "사업자는 환불 규정을 명확히 표시해야 한다."
]

# 3. DB 저장
for i, text in enumerate(texts):
    collection.add(
        documents=[text],
        ids=[f"doc_{i}"]
    )

print("DB 저장 완료")

# 4. 검색 테스트
query = "환불 규정"
results = collection.query(
    query_texts=[query],
    n_results=2
)

print(results)