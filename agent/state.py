from typing import TypedDict

class FinePrintState(TypedDict):
    service_name: str
    user_question: str

    primary_intent: str
    related_intents: list[str]
    is_in_scope: bool
    # True → FinePrint가 처리할 질문
    # False → FinePrint 범위 밖 질문

    terms_context: list[str]
    consumer_protection_context: list[str]

    draft_answer: str

    verification_status: str
    verification_reason: str
    missing_evidence: str
    suggested_action: str

    improvement_instruction: str
    retry_count: int

    final_answer: dict