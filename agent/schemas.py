from pydantic import BaseModel, Field

# 문제 유형 
class IntentResult(BaseModel):
    primary_intent: str = Field(
        description="사용자 문제의 핵심 원인이 되는 문제 유형"
    )

    related_intents: list[str] = Field(
        description="핵심 문제와 직접 관련된 추가 문제 유형 목록"
    )

# 검증 결과
class VerificationResult(BaseModel):
    status: str = Field(
        description="검증 결과. PASS 또는 FAIL"
    )

    reason: str = Field(
        description="답변이 근거와 부합하는지 판단한 이유"
    )

    missing_evidence: list[str] = Field(
        description="답변 생성에 부족하거나 추가로 확인해야 할 근거 목록"
    )

    suggested_action: str = Field(
        description="다음 개선 행동. RETRIEVE_AGAIN, REGENERATE, NONE 중 하나"
    )

# 결과 개선용
class ImprovementResult(BaseModel):
    improvement_instruction: str = Field(
        description=(
            "검증 실패 사유를 해결하기 위해 다음 검색 또는 "
            "답변 생성 단계에 적용할 구체적인 한국어 개선 지시"
        )
    )


class FinalAnswerResult(BaseModel):
    problem_type: str = Field(
        description="사용자가 이해할 수 있는 한국어 문제 유형"
    )

    terms_evidence: list[str] = Field(
        description="제공된 약관 근거에 실제로 존재하는 내용만 작성"
    )

    simple_explanation: str = Field(
        description=(
            "사용자 문제 상황을 쉬운 한국어로 설명. "
            "근거 부족 답변에서는 현재 문서만으로 판단하기 어려운 이유를 명시"
        )
    )

    check_items: list[str] = Field(
        description="추가 판단을 위해 사용자가 확인해야 할 사실 목록"
    )

    next_actions: list[str] = Field(
        description=(
            "근거 범위 안에서 사용자가 취할 수 있는 다음 행동. "
            "근거 부족 시 사실 확인, 자료 확인, 공식 문의 범위로 제한"
        )
    )

    required_materials: list[str] = Field(
        description="사실관계 확인 또는 공식 문의 시 준비하면 좋은 자료"
    )

    inquiry_draft: str = Field(
        description=(
            "정중한 한국어 고객센터 문의문 초안. "
            "근거 없는 권리 주장이나 환불 요구를 하지 않고 "
            "사실관계와 처리 가능 여부를 확인하는 형태"
        )
    )

    follow_up_questions: list[str] = Field(
        description="추가 판단을 위해 사용자에게 확인할 한국어 질문"
    )