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
        description=(
            "제공된 약관 근거에 실제로 존재하는 내용만 "
            "한국어로 작성한 목록"
        )
    )

    simple_explanation: str = Field(
        description="사용자 문제 상황을 쉬운 한국어로 설명"
    )

    check_items: list[str] = Field(
        description="사용자가 추가로 확인해야 할 사항을 한국어로 작성"
    )

    next_actions: list[str] = Field(
        description="사용자가 취할 수 있는 행동을 한국어로 작성"
    )

    required_materials: list[str] = Field(
        description="준비하면 좋은 자료를 한국어로 작성"
    )

    inquiry_draft: str = Field(
        description="자연스럽고 정중한 한국어 고객센터 문의문 초안"
    )

    follow_up_questions: list[str] = Field(
        description="추가 판단을 위해 사용자에게 물을 한국어 질문"
    )