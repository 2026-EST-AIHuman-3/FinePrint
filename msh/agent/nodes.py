from dotenv import load_dotenv
from .state import FinePrintState
from .schemas import IntentResult, VerificationResult, ImprovementResult, FinalAnswerResult
from langchain.chat_models import init_chat_model
try:
    from ..rag_adapter import retrieve_rag_context
except ImportError:
    # ``python msh/test_agent.py`` 방식의 기존 실행도 지원한다.
    from rag_adapter import retrieve_rag_context

load_dotenv()

INTENT_GUIDANCE = {
    "AUTO_RENEWAL": """
    자동 결제 또는 갱신 문제입니다.
    결제일, 해지 완료 시점, 다음 결제 주기, 콘텐츠 이용 여부를 중심으로 안내하세요.
    """,

    "CANCELLATION": """
    해지 문제입니다.
    해지 요청 시점과 현재 해지 상태를 중심으로 안내하세요.

    이용 종료 시점이 제공된 근거에 직접 명시된 경우에만 설명하세요.
    직접 확인되지 않으면 계정 상태 또는 공식 고객센터를 통해
    추가 확인이 필요하다고 안내하세요.

    사용자가 결제나 환불을 직접 묻지 않았다면
    환불 조건, 추가 결제, 콘텐츠 이용 여부는 포함하지 마세요.
    """,

    "REFUND": """
    환불 문제입니다.
    환불 조건, 신청 가능 기간, 이용 여부, 결제 내역을 중심으로 안내하세요.
    """,

    "PAYMENT": """
    결제 또는 청구 문제입니다.
    각 결제의 날짜, 금액, 결제 수단, 거래 내역을 중심으로 안내하세요.

    일반적인 결제 수단 조항을 사용자의 실제 중복 결제 원인으로
    추정하거나 연결하지 마세요.

    사용자가 환불이나 구독 취소를 직접 묻지 않았다면
    환불 조건과 해지 조건은 포함하지 마세요.

    중복 결제 여부나 원인이 현재 근거에서 확인되지 않으면,
    각 거래 내역을 비교하고 공식 고객센터에 확인하도록 안내하세요.

    required_materials에는 고객센터 문의 시 준비하면 좋은
    실제 결제 증빙 자료를 포함하세요.
    """,

    "PENALTY": """
    위약금 문제입니다.
    위약금 부과 조건, 계약 기간, 해지 시점, 산정 근거를 중심으로 안내하세요.
    """,

    "CONTRACT_CHANGE": """
    가격, 약관 또는 서비스 조건 변경 문제입니다.
    변경된 내용, 적용 시점, 사전 고지 여부,
    사용자가 확인해야 할 선택 사항을 중심으로 안내하세요.
    required_materials에는 가격 변경 안내 이메일,
    앱 알림, 인상 전후 결제 내역 등 실제 확인 가능한 자료를 포함하세요.
    """,

    "PRIVACY": """
    개인정보의 수집, 이용, 이전, 처리위탁,
    제3자로부터의 수집, 제3자 제공을 구분하세요.

    '제3자로부터 수집한다'는 내용을
    '제3자에게 제공한다'는 의미로 바꾸지 마세요.

    다만 근거에 '제3자 제공', '제3자에게 이전',
    또는 '개인정보를 다음 당사자와 공유한다'고
    직접 명시되어 있다면 제3자 제공 가능성을 설명할 수 있습니다.

    근거에 제공 대상이나 목적이 직접 명시되어 있다면
    그 범위 안에서만 설명하세요.

    직접적인 제3자 제공 근거가 있는데도
    '제3자 제공 여부를 확인할 수 없다'고 답하지 마세요.

    사용자 질문만으로 핵심 답변이 가능한 경우,
    check_items와 follow_up_questions는 빈 목록으로 반환하세요.

    개인정보 처리방침을 확인했는지 묻는 질문은 만들지 마세요.

    추가 질문이 꼭 필요한 경우에만,
    어떤 개인정보 항목이나 어떤 제3자 제공 대상이 궁금한지처럼
    사용자가 구체적으로 답할 수 있는 질문을 작성하세요.
    """,

    "ACCOUNT_RESTRICTION": """
    계정 정지 또는 이용 제한 문제입니다.
    계정에 표시된 정지 안내, 공식 알림, 정지 사유 확인, 복구 절차와 본인 확인에 필요한 정보를 중심으로 안내하세요.
    결제·환불·해지 내용은 질문과 직접 관련된 경우에만 포함하세요.
    """,

    "OTHER": """
    사용자 질문과 검색 근거에 직접 관련된 내용만 안내하세요.
    관련 없는 결제·환불·해지 항목을 관성적으로 포함하지 마세요.
    """,
}

INTENT_KOREAN = {
    "AUTO_RENEWAL": "자동 갱신 문제",
    "CANCELLATION": "해지 문제",
    "REFUND": "환불 문제",
    "PAYMENT": "결제 문제",
    "PENALTY": "위약금 문제",
    "CONTRACT_CHANGE": "계약 조건 변경 문제",
    "PRIVACY": "개인정보 문제",
    "ACCOUNT_RESTRICTION": "계정 정지 문제",
    "OTHER": "기타 구독 문제",
}

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
# ├─ 1차 답변 생성
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
    - PRIVACY: 개인정보 수집, 이용, 제공, 보관, 삭제, 제3자 공유
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
    - 개인정보 수집·이용·제공·보관·삭제 관련 문제
    - 구독 서비스 이용 중 발생한 소비자 문제

    구독형 서비스 소비자 문제와 관련이 없는 질문은
    is_in_scope를 False로 판단하세요.


    입력된 서비스명과 사용자 질문에 언급된 서비스 또는 상품 유형이
    명백히 일치하지 않는 경우 이를 감지하세요.

    예:
    - 서비스명: 넷플릭스
    - 질문: 정수기 렌탈 중도 해지 위약금

    이 경우 정상적인 약관 분석을 진행하지 말고,
    서비스명을 다시 확인해야 하는 입력 오류로 판단하세요.
    """

    result = intent_llm.invoke(prompt)

    return {
        "primary_intent": result.primary_intent,
        "related_intents": result.related_intents,
        "is_in_scope": result.is_in_scope
    }

# Hybrid RAG 검색
def retrieve_context(state: FinePrintState):
    result = retrieve_rag_context(
        service_name=state["service_name"],
        user_question=state["user_question"],
        improvement_instruction=state.get(
            "improvement_instruction",
            "",
        ),
        policy_urls=state.get("policy_urls"),
    )

    return {
        **result,
        "round_logs": [
            {
                "stage": "retrieve_context",
                "retry_count": state.get("retry_count", 0),
                "service_name": state["service_name"],
                "query": state["user_question"],
                "improvement_instruction": state.get(
                    "improvement_instruction",
                    "",
                ),
                "terms_context_preview": result[
                    "terms_context"
                ][:300],
                "consumer_context_preview": result[
                    "consumer_protection_context"
                ][:300],
            }
        ],
    }

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
    당신은 구독형 서비스의 약관과 소비자 보호 기준을 근거로
    사용자의 문제 상황을 설명하는 중립적인 AI 안내 도우미입니다.

    당신은 해당 서비스의 직원이나 고객센터 상담원이 아니며,
    법률 자문을 제공하는 역할도 아닙니다.
    서비스를 대신해 답변하거나 해당 서비스 소속인 것처럼 말하지 마세요.
    사용자에게 직접 설명하는 중립적인 안내 관점으로 답변하세요.

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

    다음 규칙을 지켜 답변하세요.

    1. 제공된 근거에 포함된 내용만 사용하세요.
    2. 서비스 약관과 소비자 보호 기준을 구분하여 설명하세요.
    3. 환불, 해지, 보상 가능 여부를 조건 없이 확정하지 마세요.
    4. 약관의 기준 시점을 바꾸지 마세요.
       예를 들어 약관이 "결제일로부터 7일 이내"라고 규정한 경우,
       이를 "해지 후 7일 이내"라고 바꾸어 표현하지 마세요.

    5. 조건이나 사실이 확인되지 않았다면 확인이 필요하다고 설명하세요.
    6. 소비자 보호 기준이 현재 서비스와 사용자 상황에 직접 적용되는지 불분명하면,
       이를 확정적인 권리나 환급 기준처럼 제시하지 마세요.
       적용 가능성을 설명할 필요가 없다면 해당 근거는 답변에서 생략하세요.
    7. 사용자의 주장만으로 해지 완료, 결제 원인, 콘텐츠 이용 여부 등을
       사실로 확정하지 마세요.
    8. 제공된 근거가 일반적인 약관 조건을 설명하더라도,
       그 조건을 사용자의 실제 결제 원인이나 문제 원인으로 추정하지 마세요.
    9. 실제 원인이 확인되지 않았다면 가능한 원인을 만들어 설명하지 말고,
       해지 완료 시점, 결제일, 계정 상태 등 확인이 필요한 사실만 안내하세요.
        잘못된 예:
        "자동 갱신 설정 때문에 결제되었을 수 있습니다."
        "해지가 늦게 처리되어 결제가 발생했을 가능성이 있습니다."

        올바른 예:
        "현재 근거만으로는 결제가 발생한 원인을 확인할 수 없습니다."
        "결제일 이전에 해지가 완료되었는지와 실제 결제 시점을 확인해야 합니다."
    10. 제공된 근거에 명시되지 않은 이용 종료 시점이나 처리 결과를
        일반적인 서비스 관행에 따라 추론하지 마세요.
    11. 답변은 쉽고 자연스러운 한국어로 작성하세요.
    12. 서비스 담당자처럼 인사하거나 서명하지 마세요.
    """

    response = generation_llm.invoke(prompt)

    return {
        "draft_answer": response.content,
        "round_logs": [
            {
                "stage": "generate_answer",
                "retry_count": state.get("retry_count", 0),
                "draft_answer": response.content,
                "improvement_instruction": improvement_instruction,
            }
        ],
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
    충분히 뒷받침되는지 다음 기준으로 검증하세요.

    1. 답변이 사용자 질문과 직접 관련되어 있는가?
    2. 답변의 모든 핵심 주장이 제공된 근거에서 확인되는가?
    3. 근거에 없는 조건, 사실, 권리, 보상 내용을 추가하지 않았는가?
    4. 환불이나 보상 가능성을 근거보다 강하게 확정하지 않았는가?
    5. 사용자 진술을 검증된 사실처럼 단정하지 않았는가?
    6. 근거에 없는 원인, 경위 또는 가능성을 추정하여 제시하지 않았는가?
       "가능성이 있습니다", "때문일 수 있습니다"와 같은 표현도 그 가능성이 제공된 근거에서 확인되지 않으면 근거 밖 추측으로 판단하세요.
    7. 소비자 보호 기준이 현재 서비스 유형과 사용자 상황에 직접 적용 가능한지 확인했는가?
    8. 적용 범위가 불분명한 소비자 보호 기준을 확정적인 권리나 환급 기준처럼 제시하지 않았는가?
    9. 해당 서비스의 직원, 고객센터 상담원 또는 법률 전문가인 것처럼 자신의 신분을 표현했는가?
       단순히 공식 고객센터 문의를 안내한 것은 역할 사칭으로 판단하지 마세요.
    10. 약관에 직접 명시되지 않은 이용 가능 기간, 종료 시점 또는 향후 결제 결과를 일반적인 관행으로 추론했는가?

        예:
        - "현재 결제 주기 마지막 날까지 이용할 수 있습니다."
        - "해지 이후에는 추가 결제가 발생하지 않습니다."

    11. 답변이 사용자 질문에서 묻지 않은 환불, 결제, 위약금 등의
        다른 문제로 불필요하게 확장되었는가?
    12. 약관의 "취소" 조건을 "해지 완료"나 "처리 완료"처럼
        더 강한 조건으로 바꾸어 표현했는가?
    13. 일반적인 결제 수단 조항을 사용자의 실제 중복 결제 원인으로
        추정하거나 설명했는가?
    14. 사용자가 환불 또는 구독 취소를 묻지 않았는데
        환불 조건이나 해지 조건으로 불필요하게 확장했는가?
    15. 개인정보 처리 위탁 또는 외부 업체의 처리를 제3자 제공이라고 바꾸어 표현했는가?
    16. 근거에 없는 사용자 동의, 법률 준수, 제공 대상 또는 관리 절차를 추가했는가?

    위 경우 기존 근거가 질문과 직접 관련되지 않거나 핵심 근거가 부족하면
    FAIL 및 RETRIEVE_AGAIN으로 판단하세요.
    
    위 내용이 제공된 근거에서 직접 확인되지 않으면 FAIL로 판단하세요.

    충분한 근거가 있고 답변이 근거와 일치하면 PASS로 판단하세요.
    근거 부족, 근거 밖 추측, 과도한 단정 또는 역할 사칭이 있으면 FAIL로 판단하세요.

    FAIL인 경우 suggested_action을 다음 기준으로 선택하세요.

    - 질문에 답하기 위한 핵심 근거가 부족하거나 무관하면
      RETRIEVE_AGAIN
    - 기존 근거는 충분하지만 답변의 표현, 조건 누락, 과도한 단정 또는 역할 사칭만 수정하면 되면
      REGENERATE

    RETRIEVE_AGAIN인 경우에만
    실제로 추가로 필요한 근거를 missing_evidence에 작성하세요.

    REGENERATE인 경우에는
    missing_evidence를 빈 목록으로 반환하고,
    수정해야 할 답변의 문제를 reason에 설명하세요.

    reason과 missing_evidence는 반드시 한국어로 작성하세요.

    예를 들어 사용자 질문이 계정 정지 사유에 관한 것인데,
    검색 근거와 생성 답변이 해지, 결제, 환불만 다룬다면 FAIL이며
    suggested_action은 RETRIEVE_AGAIN입니다.

    사용자의 사실관계가 아직 확인되지 않았더라도,
    제공된 근거에 명확한 조건부 기준이 있고
    답변이 그 조건을 그대로 설명하면서 추가 확인이 필요하다고 안내한다면
    근거 부족만을 이유로 FAIL로 판단하지 마세요.

    예:
    "결제일로부터 7일 이내이고 콘텐츠를 이용하지 않았다면
    환불을 요청할 수 있습니다.
    실제 해당 여부는 결제일, 해지 시점,
    이용 여부 확인이 필요합니다."

    위와 같은 조건부 안내는 PASS로 판단할 수 있습니다.

    답변이 환불을 확정하지 않고,
    근거에 제시된 조건과 확인해야 할 사실을 정확히 구분했다면
    직접 적용 사례가 없다는 이유만으로 FAIL로 판단하지 마세요.

    
    개인정보 문맥에서는 정보의 이동 방향을 반드시 구분하세요.

    - 제3자로부터 수집: 제3자 → 서비스 제공자
    - 서비스 제공업체를 통한 처리: 서비스 제공자를 대신한 업무 처리
    - 제3자 제공: 서비스 제공자 → 제3자

    초안이 이 방향을 바꾸거나 혼동했다면 FAIL로 판정하세요.

    근거에 "개인정보를 수집하거나 제공받는다"고 되어 있는데
    답변에서 "개인정보를 다른 회사에 제공한다"고 바꾸었다면 FAIL입니다.

    근거에 없는 제공 목적, 제공 대상, 동의 여부,
    법률 준수 또는 관리 절차를 추가했다면 FAIL입니다. 

    근거에 제3자 제공 또는 이전이 직접 명시되어 있는데,
    답변이 '제3자 제공 여부를 확인할 수 없다'고 부정하거나
    근거 부족으로 표현했다면 FAIL입니다.

    근거에 제공 대상과 목적이 일부 명시되어 있다면,
    그 범위 안의 설명은 허용합니다.  
    """

    result = verification_llm.invoke(prompt)

    return {
        "verification_status": result.status,
        "verification_reason": result.reason,
        "missing_evidence": result.missing_evidence,
        "suggested_action": result.suggested_action,
        "round_logs": [
            {
                "stage": "verify_answer",
                "retry_count": state.get("retry_count", 0),
                "status": result.status,
                "reason": result.reason,
                "suggested_action": result.suggested_action,
            }
        ],
    }

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
        "round_logs": [
            {
                "stage": "improve_strategy",
                "retry_count": retry_count + 1,
                "suggested_action": suggested_action,
                "instruction": result.improvement_instruction,
            }
        ],
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

    intent_guidance = INTENT_GUIDANCE.get(
        primary_intent,
        INTENT_GUIDANCE["OTHER"]
    )

    problem_type_korean = INTENT_KOREAN.get(
        primary_intent,
        "기타 구독 문제",
    )

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

    [검증 후 재시도 횟수]
    {retry_count}

    [현재 문제 유형에 따른 작성 방향]
    {intent_guidance}

    [사용자에게 표시할 한국어 문제 유형]
    {problem_type_korean}

    problem_type에는 위 한국어 표현을 그대로 사용하세요.


    다음 원칙을 반드시 지키세요.

    1. 모든 답변은 한국어로 작성하세요.
    2. 문제 유형은 사용자가 이해할 수 있는 한국어로 표현하세요.
    3. 사용자 질문, 제공된 근거, 검증된 답변 초안에 포함된 내용만 사용하세요.
    4. 제공된 근거에 없는 원인, 절차, 기한, 권리, 보상 가능성을 추측하지 마세요.
    5. 약관 근거와 소비자 보호 기준을 구분하세요.
    6. 사용자가 제공하지 않은 사실은 확정하지 마세요.
    7. 확인되지 않은 정보는 다음 중 하나로 처리하세요.
        - 추가 확인이 필요하다고 안내
        - 고객센터 확인 요청
        - 구체적인 자리표시자 사용
    8. check_items, next_actions, required_materials, follow_up_questions에는
       현재 질문과 주요 문제 유형에 직접 관련된 내용만 포함하세요.
    9. 관련 근거가 없는 항목은 일반적인 내용으로 채우지 말고 빈 목록으로 반환하세요.
    10. 사용자가 직접 확인하거나 준비할 수 없는 내부 정보는
        required_materials에 포함하지 마세요.
    11. required_materials에는 계정 비밀번호, 인증번호, 로그인 정보 등 보안상 민감한 정보를 포함하지 마세요.
    12. 사용자에게 내부 로그인 기록이나 내부 처리 로그를 준비하라고 하지 마세요.
        내부 기록이 필요하면 고객센터에 확인을 요청하도록 안내하세요.
    13. inquiry_draft는 사용자가 고객센터에 보내는 1인칭 문의문으로 작성하세요.
    14. 확인되지 않은 정보는
        [날짜 입력], [이용 여부 입력], [상태 입력]처럼 구체적인 자리표시자를 사용하세요.
    15. 검증 상태가 FAIL이면,
        현재 확보된 문서만으로 충분한 근거를 확인하기 어렵다는 점을 명확히 안내하세요.
    16. 현재 검색 결과에서 확인되지 않은 사실을 약관이나 정책 전체에 존재하지 않는다고 표현하지 마세요.

        "없다", "명시되어 있지 않다", "포함되어 있지 않다" 대신
        "현재 검색된 근거에서는 확인하지 못했다"라고 표현하세요.
    17. terms_evidence에는 제공된 약관 근거에서
        사용자 질문과 직접 관련된 문장만 선택하여 작성하세요.

        여러 조항의 내용을 하나의 새로운 문장으로 합치거나
        요약하여 새로운 근거를 만들지 마세요.

        원문의 조건, 기준 시점, 예외 사항을 바꾸지 말고
        가능한 한 제공된 문장에 가깝게 작성하세요.

        직접 관련된 약관 근거가 없다면 빈 목록으로 반환하세요.

        terms_evidence는 근거 내용을 새롭게 요약한 문장이 아니라,
        제공된 원문에서 직접 선택한 문장이어야 합니다.

        여러 문장의 정보를 합쳐 하나의 새로운 문장으로 만들지 마세요.
    18. source_references에는 최종 답변에서 실제로 사용한 근거의 출처만 작성하세요.

        - 서비스 약관은 서비스명, 문서명, 확인된 조항 번호를 작성하세요.
        - 법률 또는 지침은 문서명과 확인된 조·항을 작성하세요.
        - 조항 번호는 제공된 근거에서 직접 확인되는 경우에만 작성하세요.
        - 조항 번호가 확인되지 않으면 임의로 만들지 마세요.
        - 검색만 되었지만 최종 답변에 사용하지 않은 문서는 포함하지 마세요.
        - 동일한 출처는 중복해서 작성하지 마세요.
        - 실제 사용한 출처가 없다면 빈 목록으로 반환하세요.
        - 문서에 섹션명이나 조항 제목이 확인되면 문서명만 작성하지 말고 해당 섹션명 또는 조항 제목까지 작성하세요.

            예:
            - "Netflix 이용약관 2.7. Refund Requests"
            - "콘텐츠이용자 보호지침 제17조 제1항"

    19. source_references에는 내부 파일 경로나 DB 저장 경로를 작성하지 마세요.

        잘못된 예:
        - RAG/terms/넷플릭스/개인정보처리방침.pdf

        올바른 예:
        - Netflix 개인정보 처리방침 - 개인정보를 이전하는 대상
        - Netflix 개인정보 처리방침 섹션 B: 귀하의 권리 및 통제권

    약관에 명시되지 않은 서비스 이용 종료 시점이나 처리 결과를
    일반적인 관행에 따라 보완하여 설명하지 마세요.

    정확한 시점이나 처리 결과가 제공된 근거에서 확인되지 않으면,
    추가 확인이 필요하다고 안내하세요.


    검증된 답변 초안의 의미 범위를 넘어 새로운 사실이나 결론을 추가하지 마세요.

    최종 답변 생성은 검증된 초안을 구조화하고 쉽게 표현하는 작업입니다.
    초안에 없는 서비스 이용 기간, 처리 결과, 절차, 권리를 새롭게 생성하지 마세요.

    약관 원문과 검증된 초안이 서로 다르게 보이는 경우,
    더 강한 결론을 만들지 말고 추가 확인이 필요하다고 작성하세요.

    관련 약관에 다른 문제 유형의 내용이 함께 검색되더라도,
    사용자 질문에 직접 답하지 않는 조항은 terms_evidence와 최종 답변에서 제외하세요.
    related_intents에 포함되었다는 이유만으로 해당 내용을 추가하지 마세요.
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

    intent_guidance = INTENT_GUIDANCE.get(
        primary_intent,
        INTENT_GUIDANCE["OTHER"],
    )

    problem_type_korean = INTENT_KOREAN.get(
        primary_intent,
        "기타 구독 문제",
    )

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

    [현재 문제 유형에 따른 작성 방향]
    {intent_guidance}

    [사용자에게 표시할 한국어 문제 유형]
    {problem_type_korean}

    problem_type에는 위 한국어 표현을 그대로 사용하세요.

    사용자에게 근거 부족 상태를 명확하게 안내하세요.

    다음 원칙을 반드시 지키세요.

    1. 모든 답변은 반드시 한국어로 작성하세요.
    2. 현재 확인된 근거에 실제로 존재하는 내용만 설명하세요.
    3. 환불 가능, 위법, 보상 가능 여부를 확정하지 마세요.
    4. 근거에 없는 대응 방법을 새롭게 제안하지 마세요.
    5. 확인되지 않은 세부 내용은 현재 검색된 근거에서는 확인하지 못했다고 명확히 표현하세요.
    6. simple_explanation에는 확인된 핵심 사실과 현재 근거에서 확인하지 못한 세부 정보를 구분하여 설명하세요.
    7. next_actions는 사실관계 확인, 추가 자료 확인, 공식 고객센터 문의 범위로 제한하세요.
    8. 근거가 없는 환불 요청, 결제 취소, 신고, 이의 제기 등의 행동을 직접 권고하지 마세요.
    9. 문의문 초안은 특정 권리를 주장하거나 환불을 요구하는 내용이 아니라, 문제 상황과 사실관계를 설명하고 관련 정책 및 처리 가능 여부를 확인하는 형태로 작성하세요.
    10. 사용자가 제공하지 않은 사실관계를 확정하지 말고, 확인되지 않은 정보는 추가 확인이 필요한 항목으로 표현하세요.

    현재 검색된 근거에서 확인되지 않은 사실을
    약관이나 정책 전체에 존재하지 않는다고 단정하지 마세요.

    "없다", "명시되어 있지 않다", "포함되어 있지 않다" 대신
    "현재 검색된 근거에서는 확인하지 못했다"라고 표현하세요.

    
    check_items, next_actions, required_materials, follow_up_questions에는
    현재 질문과 주요 문제 유형에 직접 관련된 내용만 포함하세요.

    
    사용자가 직접 준비할 관련 자료가 없다면
    required_materials는 빈 목록으로 반환하세요.

    
    terms_evidence에는 현재 확인된 약관 근거 중
    사용자 질문과 직접 관련된 문장만 작성하세요.

    여러 근거를 합쳐 새로운 문장으로 요약하거나 해석하지 마세요.
    직접 관련된 약관 근거가 없으면 빈 목록으로 반환하세요.

    
    약관에 명시되지 않은 서비스 이용 종료 시점이나 처리 결과를
    일반적인 관행에 따라 보완하여 설명하지 마세요.

    정확한 시점이나 처리 결과가 제공된 근거에서 확인되지 않으면,
    추가 확인이 필요하다고 안내하세요.


    현재 확인된 근거의 의미 범위를 넘어 새로운 사실이나 결론을 추가하지 마세요.

    최종 답변은 현재 확인된 근거와 검증 실패 사유를 사용자가 이해하기 쉽게 구조화하는 작업입니다.
    
    현재 확인된 근거에 없는 서비스 이용 기간, 처리 결과, 절차 또는 권리를 새롭게 생성하지 마세요.

    약관 원문과 검증된 초안이 서로 다르게 보이는 경우,
    더 강한 결론을 만들지 말고 추가 확인이 필요하다고 작성하세요.


    고객센터 문의를 안내하는 경우,
    사용자가 실제로 준비할 수 있는 관련 증빙 자료가 있다면
    required_materials를 빈 목록으로 두지 마세요.

    required_materials에는
    결제 내역, 영수증, 화면 캡처, 이메일, 문의 기록처럼
    사용자가 직접 확보하거나 보유할 수 있는 실제 자료만 작성하세요.

    required_materials에는 계정 비밀번호, 인증번호,
    로그인 정보 등 보안상 민감한 정보를 포함하지 마세요.

    근거 부족 경로에 도달했더라도,
    검색된 문서에서 직접 확인되는 핵심 사실까지
    '확인할 수 없다'고 부정하지 마세요.

    사용자 질문의 핵심에 답할 수 있는 직접 근거가 있다면,
    세부 목록이나 부가 정보가 부족하다는 이유만으로
    전체 판단이 불가능하다고 표현하지 마세요.

    확인된 사실과 확인되지 않은 세부 정보를 명확히 구분하세요.

        예:
        - 확인됨: 개인정보가 특정 당사자에게 이전될 수 있음
        - 미확인: 모든 제공업체의 정확한 회사명과 각 제공 항목

    source_references에는 현재 확인된 근거 중
    최종 답변에서 실제로 사용한 문서만 작성하세요.

    문서명과 조항 번호가 제공된 경우에만 그대로 작성하고,
    확인할 수 없는 조항 번호는 임의로 생성하지 마세요.

    근거 부족 경로라도 실제로 확인된 출처가 있다면 포함하고,
    직접 관련된 출처가 없다면 빈 목록으로 반환하세요.
    
    source_references에는 내부 파일 경로나 DB 저장 경로를 작성하지 마세요.

        잘못된 예:
        - RAG/terms/넷플릭스/개인정보처리방침.pdf

        올바른 예:
        - Netflix 개인정보 처리방침 - 개인정보를 이전하는 대상
        - Netflix 개인정보 처리방침 섹션 B: 귀하의 권리 및 통제권
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
                "해당 질문은 FinePrint가 지원하는 구독형 서비스의 "
                "약관, 해지, 환불, 자동결제, 결제, 개인정보, 계정 정지 및 "
                "정책 관련 소비자 문제 범위를 벗어납니다."
            )
        }
    }
