# FinePrint
RAG-based AI Agent for analyzing subscription service terms and policies.

PDF 파싱 및 청킹, 임베딩 후 ChromaDB에 저장하는 py파일입니다. (PDF_Test.py)
RAG에 자료를 넣어둔 후 py파일을 실행합니다.

=================================================================================

# DB 모듈

## 사용 가능한 함수

1.
``` 
check_document_exists(service_name)
```
- 해당 서비스가 DB에 존재하는지 확인

- True / False 형태로 반환

2.
```
ingest_from_url(
    url,
    service_name,
    extracted_text
)
```
- URL에서 추출한 텍스트를 DB에 저장

3.
```
ingest_from_pasted_text(
    service_name,
    pasted_text
)
```
- 사용자가 붙여넣은 약관을 DB에 저장
