from pydantic import BaseModel, Field

# 문제 유형 
class IntentResult(BaseModel):
    primary_intent: str = Field(
        description="사용자 문제의 핵심 원인이 되는 문제 유형"
    )

    related_intents: list[str] = Field(
        description="핵심 문제와 직접 관련된 추가 문제 유형 목록"
    )

    is_in_scope: bool = Field(
        description=(
            "사용자 질문이 구독형 서비스의 약관, 결제, 자동갱신, "
            "해지, 환불, 위약금, 계약 조건 등 소비자 문제와 관련되면 True, "
            "관련이 없으면 False"
        )
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
            "제공된 약관 근거 중 현재 사용자 질문과 직접 관련된 "
            "근거 문장만 작성. "
            "여러 근거를 합쳐 새로운 문장으로 요약하거나 해석하지 말 것. "
            "원문의 조건, 기준 시점, 의미를 바꾸지 말고 "
            "가능한 한 제공된 문장에 가깝게 작성. "
            "직접 관련된 약관 근거가 없으면 빈 목록"
        )
    )

    source_references: list[str] = Field(
        description=(
            "최종 답변에 실제로 사용한 약관, 법률 또는 지침의 사용자 표시용 출처 목록. "
            "내부 파일 경로, DB 경로, 폴더명은 작성하지 말 것. "
            "서비스명, 문서명, 확인 가능한 조항명 또는 섹션명을 작성. "
            "관련 출처가 없으면 빈 목록"
        )
    )

    simple_explanation: str = Field(
        description=(
            "사용자 문제 상황을 쉬운 한국어로 설명. "
            "근거가 부족하면 현재 검색된 자료 범위에서 확인하기 어렵다고 표현. "
            "약관이나 정책 전체에 해당 내용이 없다고 단정하지 말 것"
        )
    )

    check_items: list[str] = Field(
        description=(
            "현재 사용자 질문과 문제 유형에 직접 관련된 확인 항목. "
            "약관 관련한 내용은 제외할 것. "
            "관련 내용이 없으면 빈 목록"
        )
    )

    next_actions: list[str] = Field(
        description=(
            "근거 범위 안에서 사용자가 실제로 취할 수 있는 다음 행동. "
            "관련 근거가 없으면 빈 목록"
        )
    )

    required_materials: list[str] = Field(
        description=(
            "현재 문제를 확인하거나 고객센터에 문의할 때 "
            "사용자가 실제로 준비하면 도움이 되는 증빙 자료 목록. "
            "검색 근거에 직접 언급되지 않았더라도, 사용자가 이미 보유하거나 "
            "직접 확보할 수 있는 결제 내역, 영수증, 화면 캡처, 이메일, 문의 내역 등은 포함 가능. "
            "'결제일 정보'처럼 추상적으로 쓰지 말고 "
            "'두 건의 결제 내역 또는 영수증', "
            "'넷플릭스 계정의 결제 내역 화면 캡처'처럼 실제 자료 형태로 작성. "
            "고객센터 연락처, 웹사이트 주소, 법령, 사업자 내부 로그는 포함하지 말 것. "
            "비밀번호, 인증번호, 계정 로그인 정보와 같은 보안 정보는 절대 포함하지 말 것. "
            "실제로 준비할 수 있는 관련 자료가 전혀 없을 때만 빈 목록"
        )
    )

    inquiry_draft: str = Field(
        description=(
            "사용자가 서비스 고객센터에 직접 보내는 "
            "1인칭 관점의 정중한 한국어 문의문 초안. "
            "사용자 질문에 포함된 진술도 검증된 사실로 확정하지 말 것. "
            "사용자가 말했다는 이유만으로 해지 완료 여부, 결제일, "
            "콘텐츠 이용 여부, 환불 조건 충족 여부를 사실형 문장으로 옮기지 말 것. "
            "확인되지 않은 정보는 [결제 날짜 입력], [취소 시점 입력], "
            "[이용 여부 입력]처럼 구체적인 자리표시자로 작성. "
            "근거 없는 권리 주장이나 환불 요구를 하지 않고 "
            "사실관계와 처리 가능 여부를 확인하는 형태"
        )
    )

    follow_up_questions: list[str] = Field(
        description=(
            "현재 문제 판단에 실제로 필요한 정보를 사용자에게 묻는 한국어 질문. "
            "'확인하셨나요?'처럼 단순 확인 여부를 묻지 말고, "
            "'결제일은 언제인가요?', '구독 취소는 언제 진행했나요?', "
            "'결제 후 콘텐츠를 이용한 적이 있나요?'처럼 "
            "구체적인 사실이나 값을 답할 수 있도록 작성. "
            "추가 질문이 필요하지 않으면 빈 목록"
        )
    )