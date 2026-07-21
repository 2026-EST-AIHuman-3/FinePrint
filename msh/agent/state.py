from typing import TypedDict, Annotated
from operator import add

class FinePrintState(TypedDict):
    service_name: str
    user_question: str
    # 선택 입력: 사용자가 직접 지정한 공식 약관/개인정보처리방침 URL
    # 예: {"terms": "https://...", "privacy": "https://..."}
    policy_urls: dict[str, str]

    primary_intent: str
    related_intents: list[str]
    is_in_scope: bool
    # True → FinePrint가 처리할 질문
    # False → FinePrint 범위 밖 질문

    terms_context: str
    consumer_protection_context: str
    knowledge_base_status: dict

    draft_answer: str

    verification_status: str
    verification_reason: str
    missing_evidence: str
    suggested_action: str

    improvement_instruction: str
    retry_count: int
    round_logs: Annotated[list[dict], add]

    final_answer: dict
