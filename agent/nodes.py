from dotenv import load_dotenv
from agent.state import FinePrintState
from agent.schemas import IntentResult, VerificationResult, ImprovementResult, FinalAnswerResult
from langchain.chat_models import init_chat_model
from rag_adapter import retrieve_rag_context

load_dotenv()

judgment_llm = init_chat_model(
    "gpt-4o",
    temperature=0
)
# judgment_llm
# ├─ 질문 의도 분류
# └─ 근거 검증

# → "판단"하는 작업
# → 같은 입력이면 최대한 같은 결과가 중요
# → temperature = 0

generation_llm = init_chat_model(
    "gpt-4o",
    temperature=0.3
)
# generation_llm
# ├─ 개선 전략 작성
# └─ 최종 답변 작성

# → 자연어를 "생성"하는 작업
# → 어느 정도 표현 유연성 허용
# → temperature = 0.3

intent_llm = judgment_llm.with_structured_output(IntentResult)
verification_llm = judgment_llm.with_structured_output(VerificationResult)
improvement_llm = generation_llm.with_structured_output(ImprovementResult)
final_answer_llm = generation_llm.with_structured_output(FinalAnswerResult)

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
    - ACCOUNT_RESTRICTION: 계정 정지, 이용 제한, 접근 차단, 서비스 이용 중단
    - OTHER: 위 유형에 해당하지 않는 기타 문제

    사용자 문제의 핵심 원인이 되는 primary_intent 하나를 선택하세요.

    핵심 문제와 직접 관련된 다른 문제 유형이 있다면
    related_intents에 포함하세요.

    primary_intent와 related_intents에 사용하는 값은
    반드시 위 문제 유형 중에서 선택하세요.

    또한 사용자 질문이 FinePrint의 서비스 범위에 해당하는지 판단하세요.

    다음과 관련된 질문은 is_in_scope를 True로 판단하세요.
    - 구독형 서비스 약관 및 정책
    - 자동결제 또는 자동갱신
    - 해지 및 구독 취소
    - 환불
    - 결제 또는 청구 문제
    - 위약금 또는 중도해지 비용
    - 계약 및 서비스 조건 변경
    - 구독 서비스 이용 중 발생한 소비자 문제

    구독형 서비스 소비자 문제와 관련이 없는 질문은
    is_in_scope를 False로 판단하세요.
    """

    result = intent_llm.invoke(prompt)

    return {
        "primary_intent": result.primary_intent,
        "related_intents": result.related_intents,
        "is_in_scope": result.is_in_scope
    }

# Hybrid RAG 검색
def retrieve_context(state: FinePrintState):
    return retrieve_rag_context(
        service_name=state["service_name"],
        user_question=state["user_question"],
        improvement_instruction=state.get(
            "improvement_instruction",
            "",
        ),
    )

# 쉬운 말 / 답변 생성
def generate_answer(state: FinePrintState):  
    service_name = state["service_name"]
    user_question = state["user_question"]
    primary_intent = state["primary_intent"]

    terms_context = state["terms_context"]
    consumer_context = state["consumer_protection_context"]

    improvement_instruction = state.get(
        "improvement_instruction",
        ""
    )

    prompt = f"""
    당신은 FinePrint의 1차 답변 생성 Agent입니다.

    [서비스명]
    {service_name}

    [사용자 질문]
    {user_question}

    [주요 문제 유형]
    {primary_intent}

    [관련 약관 근거]
    {terms_context}

    [소비자 보호 근거]
    {consumer_context}

    [이전 검증 결과에 따른 개선 지시]
    {improvement_instruction}

    제공된 근거만 사용해 사용자 질문에 직접 답하세요.

    다음 원칙을 지키세요.

    1. 모든 답변은 한국어로 작성하세요.
    2. 약관 근거와 소비자 보호 근거를 구분해서 설명하세요.
    3. 제공된 근거에 없는 사실을 추측하지 마세요.
    4. 환불 가능 여부 등을 근거 없이 확정하지 마세요.
    5. 근거가 부족한 부분은 추가 확인이 필요하다고 표현하세요.
    6. 개선 지시가 있다면 반드시 반영하세요.
    7. 개선 지시가 없다면 최초 답변을 생성하세요.

    근거를 요약할 때 원문의 의미를 확대하거나 바꾸지 마세요.
    특히 "다른 등록 결제 수단으로 청구할 수 있음"을 "결제 수단을 자동으로 갱신함"으로 표현하지 마세요.
    """

    response = generation_llm.invoke(prompt)

    return {
        "draft_answer": response.content
    }

# 근거 검증 Agent
def verify_answer(state: FinePrintState):
    user_question = state["user_question"]
    primary_intent = state["primary_intent"]

    terms_context = state["terms_context"]
    consumer_context = state["consumer_protection_context"]
    draft_answer = state["draft_answer"]

    prompt = f"""
    당신은 FinePrint의 근거 검증 Agent입니다.

    [사용자 질문]
    {user_question}

    [주요 문제 유형]
    {primary_intent}

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
    5. 검색된 근거가 사용자의 실제 질문과 직접 관련되어 있는가
    6. 생성된 답변이 사용자의 질문과 주요 문제 유형에 직접 답하고 있는가
    7. 답변과 근거가 서로 일치하더라도, 사용자의 질문과 무관한 내용이면 FAIL로 판단하세요.
    8. 소비자 보호 기준이 해당 서비스 유형 또는 업종에 실제로 적용되는지 확인하세요.
       검색 청크에 적용 대상이나 업종 정보가 없으면 일반적으로 적용 가능한 기준이라고 단정하지 마세요.
    
    reason과 missing_evidence는 반드시 한국어로 작성하세요.
       
    예를 들어, 사용자 질문이 계정 정지 사유에 관한 것인데
    검색 근거와 생성 답변이 해지, 결제, 환불만 다룬다면 FAIL입니다.

    충분한 근거가 있다면 PASS,
    근거 부족 또는 근거 밖 추측이 있다면 FAIL로 판단하세요.

    FAIL인 경우 부족한 근거를 missing_evidence에 작성하고,
    추가 문서 검색이 필요하면 RETRIEVE_AGAIN,
    근거는 충분하지만 답변 표현 수정이 필요하면 REGENERATE를 선택하세요.

    사용자의 사실관계가 아직 확인되지 않았더라도,
    제공된 근거에 명확한 조건부 기준이 있고
    답변이 그 조건을 그대로 설명하면서 추가 확인이 필요하다고 안내한다면
    근거 부족만을 이유로 FAIL로 판단하지 마세요.

    예:
    "결제일로부터 7일 이내이고 콘텐츠를 이용하지 않았다면 환불을 요청할 수 있습니다.
    실제 해당 여부는 결제일, 해지 시점, 이용 여부 확인이 필요합니다."

    위와 같은 조건부 안내는 PASS로 판단할 수 있습니다.

    답변이 환불을 확정하지 않고,
    근거에 제시된 조건과 확인해야 할 사실을 정확히 구분했다면
    직접 적용 사례가 없다는 이유만으로 FAIL로 판단하지 마세요.
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

    검증 Agent의 suggested_action에 해당하는 개선 지시만 작성하세요.

    제목이나 RETRIEVE_AGAIN, REGENERATE 같은 분류명을 출력하지 말고,
    실제로 다음 단계에서 수행할 구체적인 지시만 작성하세요.

    RETRIEVE_AGAIN인 경우:
    추가로 찾아야 할 정보와 검색 방향을 구체적으로 작성하세요.

    REGENERATE인 경우:
    기존 근거 범위 안에서 수정해야 할 답변 표현,
    출력 방식 또는 주의사항을 구체적으로 작성하세요.

    검색 방향은 공식 약관, 공식 정책, 법령, 정부·공공기관 지침으로 제한하세요.
    커뮤니티 게시글, 리뷰, 사용자 경험 사례는 검색 근거로 제안하지 마세요.
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
    9. 문의문 초안은 반드시 사용자가 서비스 고객센터에 직접 문의하는 1인칭 관점으로 작성하세요.
       고객센터가 사용자에게 답변하는 형태로 작성하지 마세요.

    10. 사용자가 제공하지 않은 사실은 절대 확정하거나 추정하지 마세요.
        특히 다음 정보가 확인되지 않았다면 사실처럼 작성하지 마세요.
        - 해지 완료 여부
        - 해지 날짜와 처리 시점
        - 결제 날짜와 결제 원인
        - 콘텐츠 이용 여부
        - 환불 조건 충족 여부

    11. 사용자 질문에 포함된 표현도 확인된 사실이 아니라
        사용자의 주장으로만 취급하세요.
        예를 들어 "해지했는데 결제됐다"는 표현만으로
        해지가 정상 완료되었다고 판단하지 마세요.

    12. 확인되지 않은 정보는 반드시 다음 중 하나의 방식으로 작성하세요.
        - 대괄호 자리표시자 사용
        - 고객센터에 확인 요청
        - 사용자가 직접 입력할 항목으로 제시

    13. 문의문에 환불 조건이 포함되더라도,
        사용자가 그 조건을 충족했다고 단정하지 마세요.

    잘못된 예:
    "구독 취소 후 넷플릭스 콘텐츠에 접근하지 않았습니다."

    올바른 예:
    "구독 취소 후 콘텐츠 이용 여부는 [이용 여부 입력]입니다."

    또는:
    "구독 취소 후 콘텐츠 이용 기록도 함께 확인 부탁드립니다."

    14. required_materials에는 사용자가 실제로 준비할 수 있는 자료만 포함하세요.
        법령, 소비자 보호 기준, 내부 정책 문서는 포함하지 마세요.

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
    2. 현재 확인된 근거에 실제로 존재하는 내용만 설명하세요.
    3. 환불 가능, 위법, 보상 가능 여부를 확정하지 마세요.
    4. 근거에 없는 대응 방법을 새롭게 제안하지 마세요.
    5. 확인되지 않은 내용은 확인할 수 없다고 명확히 표현하세요.
    6. simple_explanation에는 현재 확보된 문서만으로 판단하기 어려운 이유를 반드시 직접 설명하세요.
    7. next_actions는 사실관계 확인, 추가 자료 확인, 공식 고객센터 문의 범위로 제한하세요.
    8. 근거가 없는 환불 요청, 결제 취소, 신고, 이의 제기 등의 행동을 직접 권고하지 마세요.
    9. 문의문 초안은 특정 권리를 주장하거나 환불을 요구하는 내용이 아니라, 문제 상황과 사실관계를 설명하고 관련 정책 및 처리 가능 여부를 확인하는 형태로 작성하세요.
    10. 현재 확보된 문서만으로 충분한 근거를 확인하기 어렵다는 점을 명확히 안내하세요.
    11. 사용자가 제공하지 않은 사실관계를 확정하지 말고, 확인되지 않은 정보는 추가 확인이 필요한 항목으로 표현하세요.
    """

    result = final_answer_llm.invoke(prompt)

    return {
        "final_answer": result.model_dump()
    }

# 서비스 범위 밖 질문 응답
def generate_out_of_scope_answer(state: FinePrintState):
    return {
        "final_answer": {
            "message": (
                "해당 질문은 FinePrint가 지원하는 "
                "구독형 서비스의 약관, 해지, 환불, 자동결제, "
                "결제 및 정책 관련 소비자 문제 범위를 벗어납니다."
            )
        }
    }