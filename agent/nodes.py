from dotenv import load_dotenv
from agent.state import FinePrintState
from agent.schemas import IntentResult, VerificationResult, ImprovementResult, FinalAnswerResult
from langchain.chat_models import init_chat_model

load_dotenv()

llm = init_chat_model("gpt-4o")
intent_llm = llm.with_structured_output(IntentResult)
verification_llm = llm.with_structured_output(VerificationResult)
improvement_llm = llm.with_structured_output(ImprovementResult)
final_answer_llm = llm.with_structured_output(FinalAnswerResult)

# 질문 의도 분류 모듈
def classify_intent(state: FinePrintState):
    service_name = state["service_name"]
    user_question = state["user_question"]

    prompt = f"""
    당신은 구독형 서비스 이용 중 발생한 소비자 문제의 의도를 분류하는 AI입니다.

    서비스명:
    {service_name}

    사용자 문제 상황:
    {user_question}

    문제 유형:
    - AUTO_RENEWAL: 자동결제, 자동갱신, 해지 후 결제 지속
    - CANCELLATION: 구독 해지, 취소, 계약 종료
    - REFUND: 환불, 결제 취소, 금액 반환
    - PAYMENT: 중복결제, 잘못된 금액 청구, 예상하지 못한 결제
    - PENALTY: 위약금, 중도해지 비용
    - CONTRACT_CHANGE: 가격, 약관, 서비스 조건 변경
    - OTHER: 위 유형에 해당하지 않는 기타 문제

    사용자 문제의 핵심 원인이 되는 primary_intent 하나를 선택하세요.

    핵심 문제와 직접 관련된 다른 문제 유형이 있다면
    related_intents에 포함하세요.

    primary_intent와 related_intents에 사용하는 값은
    반드시 위 문제 유형 중에서 선택하세요.
    """

    result = intent_llm.invoke(prompt)

    return {
        "primary_intent": result.primary_intent,
        "related_intents": result.related_intents,
    }


# Hybrid RAG 검색
def retrieve_context(state: FinePrintState):
    # 임시 값!!
    return {
        "terms_context": [
            "해지 시 현재 결제 주기 종료일까지 서비스를 이용할 수 있습니다."
        ],
        "consumer_protection_context": [
            "계속거래 계약 관련 소비자 보호 기준입니다."
        ],
    }

# 쉬운 말 / 답변 생성
def generate_answer(state: FinePrintState):
    # 임시 답변!!
    return {
        "draft_answer": (
            "해지 이후 결제된 금액은 무조건 전액 환불받을 수 있습니다."
        )
    }

# 근거 검증 Agent
def verify_answer(state: FinePrintState):
    terms_context = state["terms_context"]
    consumer_context = state["consumer_protection_context"]
    draft_answer = state["draft_answer"]

    prompt = f"""
    당신은 FinePrint의 근거 검증 Agent입니다.

    [약관 근거]
    {terms_context}

    [소비자 보호 근거]
    {consumer_context}

    [생성된 1차 답변]
    {draft_answer}

    생성된 답변의 주요 주장들이 제공된 근거로
    충분히 뒷받침되는지 검증하세요.

    다음 사항을 확인하세요.

    1. 답변에 근거 문서에 없는 사실이 포함되어 있는가
    2. 환불 가능, 위법, 보상 가능 등 확정적인 표현에 직접 근거가 있는가
    3. 사용자에게 제안한 다음 행동이 근거와 모순되지 않는가
    4. 답변에 필요한 핵심 근거가 누락되어 있는가

    충분한 근거가 있다면 PASS,
    근거 부족 또는 근거 밖 추측이 있다면 FAIL로 판단하세요.

    FAIL인 경우 부족한 근거를 missing_evidence에 작성하고,
    추가 문서 검색이 필요하면 RETRIEVE_AGAIN,
    근거는 충분하지만 답변 표현 수정이 필요하면 REGENERATE를 선택하세요.
    """

    result = verification_llm.invoke(prompt)

    return {
        "verification_status": result.status,
        "verification_reason": result.reason,
        "missing_evidence": result.missing_evidence,
        "suggested_action": result.suggested_action,
    }

# 근거 검증 루프
# 근거 검증 실패 개선 전략 생성
def improve_strategy(state: FinePrintState):
    service_name = state["service_name"]
    user_question = state["user_question"]

    verification_reason = state["verification_reason"]
    missing_evidence = state["missing_evidence"]
    suggested_action = state["suggested_action"]
    retry_count = state["retry_count"]

    prompt = f"""
    당신은 FinePrint의 검증 실패 개선 전략을 생성하는 AI입니다.

    [서비스명]
    {service_name}

    [사용자 문제 상황]
    {user_question}

    [검증 실패 사유]
    {verification_reason}

    [부족한 근거]
    {missing_evidence}

    [검증 Agent 권장 행동]
    {suggested_action}

    현재 검증 실패 사유를 해결하기 위해
    다음 검색 또는 답변 생성 단계에서 적용할
    구체적인 개선 지시를 작성하세요.

    반드시 검증 실패 사유와 부족한 근거를 기반으로 작성하세요.
    개선 지시는 반드시 한국어로 작성하세요.

    새로운 사실을 추측하거나 답변을 직접 생성하지 마세요.

    RETRIEVE_AGAIN인 경우:
    추가로 찾아야 할 정보와 검색 방향을 구체적으로 작성하세요.

    REGENERATE인 경우:
    기존 근거 범위 안에서 수정해야 할 답변 표현,
    출력 방식 또는 주의사항을 구체적으로 작성하세요.
    """

    result = improvement_llm.invoke(prompt)

    return {
        "improvement_instruction": result.improvement_instruction,
        "retry_count": retry_count + 1,
    }

# 최종 답변 생성
def generate_final_answer(state: FinePrintState):
    service_name = state["service_name"]
    user_question = state["user_question"]

    primary_intent = state["primary_intent"]
    related_intents = state["related_intents"]

    terms_context = state["terms_context"]
    consumer_context = state["consumer_protection_context"]

    draft_answer = state["draft_answer"]

    verification_status = state["verification_status"]
    verification_reason = state["verification_reason"]
    retry_count = state["retry_count"]

    prompt = f"""
    당신은 구독형 서비스 소비자 문제 해결을 지원하는
    FinePrint AI Agent입니다.

    검증을 완료한 정보만 사용하여
    사용자에게 제공할 최종 답변을 생성하세요.

    [서비스명]
    {service_name}

    [사용자 문제 상황]
    {user_question}

    [주요 문제 유형]
    {primary_intent}

    [관련 문제 유형]
    {related_intents}

    [관련 약관 근거]
    {terms_context}

    [소비자 보호 근거]
    {consumer_context}

    [검증된 답변 초안]
    {draft_answer}

    [최종 검증 상태]
    {verification_status}

    [검증 결과 설명]
    {verification_reason}

    [재검색 횟수]
    {retry_count}

    다음 원칙을 반드시 지키세요.

    1. 모든 답변은 반드시 한국어로 작성하세요.
    2. 문제 유형도 사용자가 이해할 수 있는 한국어로 표현하세요.
    3. 제공된 근거에 없는 사실을 추측하지 마세요.
    4. 환불 가능, 위법, 보상 가능 여부를 근거 없이 확정하지 마세요.
    5. 약관 근거와 소비자 보호 기준을 혼동하지 마세요.
    6. 사용자가 실제로 확인하고 행동할 수 있도록 구체적으로 안내하세요.
    7. 근거가 부족한 부분은 추가 확인이 필요하다고 명확히 표현하세요.
    8. 문의문 초안은 사용자 상황에 맞게 자연스럽고 정중한 한국어로 작성하세요.

    검증 상태가 FAIL인 경우,
    확인되지 않은 내용을 사실처럼 작성하지 마세요.

    현재 확보된 문서만으로 판단하기 어려운 부분은
    "현재 확보된 문서만으로는 충분한 근거를 확인하기 어렵습니다."
    라고 명확히 안내하세요.
    """

    result = final_answer_llm.invoke(prompt)

    return {
        "final_answer": result.model_dump() # Pydantic 객체를 딕셔너리로 바꿈
    }

# 근거 부족 최종 답변 생성 모듈
def generate_insufficient_evidence_answer(
    state: FinePrintState
):
    service_name = state["service_name"]
    user_question = state["user_question"]

    primary_intent = state["primary_intent"]
    related_intents = state["related_intents"]

    terms_context = state["terms_context"]
    consumer_context = state["consumer_protection_context"]

    verification_reason = state["verification_reason"]
    missing_evidence = state["missing_evidence"]

    prompt = f"""
    당신은 구독형 서비스 소비자 문제 해결을 지원하는
    FinePrint AI Agent입니다.

    현재 답변은 근거 검증을 통과하지 못했으며,
    추가 검색 이후에도 충분한 근거를 확보하지 못했습니다.

    [서비스명]
    {service_name}

    [사용자 문제 상황]
    {user_question}

    [주요 문제 유형]
    {primary_intent}

    [관련 문제 유형]
    {related_intents}

    [현재 확인된 약관 근거]
    {terms_context}

    [현재 확인된 소비자 보호 근거]
    {consumer_context}

    [검증 실패 사유]
    {verification_reason}

    [부족한 근거]
    {missing_evidence}

    사용자에게 근거 부족 상태를 명확하게 안내하세요.

    다음 원칙을 반드시 지키세요.

    1. 모든 답변은 반드시 한국어로 작성하세요.
    2. 현재 확인된 근거에 있는 내용만 설명하세요.
    3. 환불 가능, 위법, 보상 가능 여부를 확정하지 마세요.
    4. 근거에 없는 대응 방법을 새롭게 제안하지 마세요.
    5. 확인되지 않은 내용은 확인할 수 없다고 명확히 표현하세요.
    6. 추가 판단에 필요한 정보와 사용자에게 확인할 질문을 중심으로 작성하세요.
    7. 현재 확보된 문서만으로 충분한 근거를 확인하기 어렵다는 점을 명시하세요.
    """

    result = final_answer_llm.invoke(prompt)

    return {
        "final_answer": result.model_dump()
    }