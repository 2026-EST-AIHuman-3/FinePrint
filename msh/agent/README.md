# FinePrint Agent
### LangGraph 기반 근거 검증 및 실패 복구 흐름 설계
: 검색된 근거와 생성 답변의 일치 여부를 검증하고, 실패 원인에 따라 재생성·재검색·근거 부족 안내로 분기하는 Agent를 설계했습니다.

## 1. 담당 역할
**LangGraph 기반 근거 검증 Agent 흐름 설계 및 구현**

- 사용자 질문의 지원 범위 및 문제 유형 분류
- Hybrid RAG 검색 결과를 Agent State에 연결
- 검색 근거를 활용한 답변 생성
- 생성 답변과 근거의 일치 여부 검증
- 실패 원인에 따른 `REGENERATE`·`RETRIEVE_AGAIN` 분기
- 최대 재시도 제한과 근거 부족 안내 경로 구현

## 2.  관련 파일

파일 구조
```
msh/
├─ agent/
│  ├─ README.md
│  ├─ __init__.py
│  ├─ nodes.py
│  ├─ schemas.py
│  ├─ state.py
│  └─ workflow.py
├─ rag_adapter.py
├─ requirements.txt
└─ test_agent.py
```

- `agent/workflow.py`: LangGraph 흐름 및 조건부 분기 구성
- `agent/nodes.py`: 의도 분류, 답변 생성, 검증 노드 구현
- `agent/state.py`: Agent 상태 정의
- `agent/schemas.py`: 구조화 출력 스키마 정의
- `../rag_adapter.py`: RAG 검색 결과를 Agent 입력 형식으로 연결
- `../test_agent.py`: Agent 통합 실행 및 테스트

## 3. Agent 동작 흐름

사용자 질문의 지원 범위와 문제 유형을 분류한 뒤,  
서비스 약관과 소비자 보호 근거를 검색해 초안 답변을 생성합니다.

생성된 답변은 별도의 검증 노드에서 실제 검색 근거와 일치하는지 확인하며,  
검증 결과와 실패 원인에 따라 최종 답변·재생성·재검색·근거 부족 안내 경로로 분기합니다.

![FinePrint Agent 동작 흐름](../../images/agent-workflow.png)
- `PASS`: 근거와 답변이 일치하면 최종 답변 생성
- `REGENERATE`: 근거는 충분하지만 표현이 부정확하면 답변만 재생성
- `RETRIEVE_AGAIN`: 판단 근거가 부족하면 검색 전략을 보완해 재검색
- `INSUFFICIENT`: 최대 재시도 후에도 근거가 부족하면 확인사항과 필요 자료 안내
- `OUT_OF_SCOPE`: 지원 범위를 벗어난 질문은 별도 안내 후 종료

## 4. State 구조

FinePrint는 질문 분류부터 근거 검색, 답변 검증, 재시도 이력까지  
하나의 `FinePrintState`에서 관리하도록 설계했습니다.

State는 크게 다음 다섯 영역으로 구성됩니다.

| 영역 | 주요 필드 | 역할 |
|---|---|---|
| 사용자 입력 | `service_name`, `user_question`, `policy_urls` | 서비스와 문제 상황, 사용자 지정 공식 URL 저장 |
| 의도 분류 | `primary_intent`, `related_intents`, `is_in_scope` | 문제 유형과 지원 범위 판단 |
| 검색 근거 | `terms_context`, `consumer_protection_context`, `knowledge_base_status` | 약관·소비자 보호 검색 결과와 DB 상태 저장 |
| 생성·검증 | `draft_answer`, `verification_status`, `missing_evidence`, `suggested_action` | 초안 답변과 검증 결과, 실패 원인 관리 |
| 재시도·출력 | `improvement_instruction`, `retry_count`, `round_logs`, `final_answer` | 개선 지시, 반복 횟수, 실행 이력, 최종 답변 관리 |

<details>
<summary><strong>FinePrintState 전체 코드 보기</strong></summary>

```python
class FinePrintState(TypedDict):
    service_name: str
    user_question: str
    policy_urls: dict[str, str]

    primary_intent: str
    related_intents: list[str]
    is_in_scope: bool

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
```
### 설계 포인트

- 모든 노드가 동일한 State를 읽고 필요한 필드만 갱신하도록 구성
- `retry_count`로 최대 재시도 횟수를 제어(2회로 설정함)
- `round_logs`에 각 검색·생성·검증 라운드의 결과를 누적
  - `round_logs`는 LangGraph reducer를 이용해 각 라운드의 로그를 덮어쓰지 않고 리스트에 누적합니다.
- `missing_evidence`와 `suggested_action`을 다음 재시도 전략에 활용
- `final_answer`는 UI에서 바로 사용할 수 있도록 구조화된 형태로 저장

</details>

## 5. 주요 노드 및 조건부 분기

### 주요 노드

| 노드 | 역할 |
|---|---|
| `classify_intent` | 사용자 질문의 주요·연관 의도를 분류하고 FinePrint의 지원 범위에 해당하는지 판단 |
| `retrieve_context` | 서비스 약관과 소비자 보호 자료를 Hybrid RAG로 검색하고 검색 결과와 실행 로그를 State에 저장 |
| `generate_answer` | 검색된 근거와 이전 검증의 개선 지시를 바탕으로 1차 답변 생성 |
| `verify_answer` | 답변의 핵심 주장이 검색 근거와 일치하는지 검증하고 후속 행동을 결정 |
| `improve_strategy` | 검증 실패 사유를 바탕으로 다음 검색 또는 답변 생성 단계에 적용할 개선 지시 생성 |
| `generate_final_answer` | 검증을 통과한 초안을 사용자에게 제공할 구조화된 최종 답변으로 변환 |
| `generate_insufficient_evidence_answer` | 재시도 후에도 근거가 부족할 경우 확인된 사실과 미확인 정보를 구분하여 안내 |
| `generate_out_of_scope_answer` | FinePrint의 지원 범위를 벗어난 질문에 안내 메시지를 제공하고 종료 |

각 노드는 `FinePrintState`를 통해 질문 분류 결과, 검색 근거,
생성 답변, 검증 결과와 재시도 정보를 공유합니다.

### 조건부 분기

| 분기 함수 | 판단 기준 | 이동 경로 |
|---|---|---|
| `route_scope` | `is_in_scope` 값 | 지원 범위이면 `retrieve_context`, 범위 밖이면 `generate_out_of_scope_answer` |
| `route_verification` | `verification_status`와 `retry_count` | 검증 통과, 개선 재시도 또는 근거 부족 답변으로 분기 |
| `route_improvement` | `suggested_action` 값 | 답변 재생성 또는 근거 재검색 경로 선택 |

| 분기 결과 | 조건 | 다음 노드 |
|---|---|---|
| `in_scope` | `is_in_scope == True` | `retrieve_context` |
| `out_of_scope` | `is_in_scope == False` | `generate_out_of_scope_answer` |
| `pass` | `verification_status == "PASS"` | `generate_final_answer` |
| `fail` | 검증 실패이며 `retry_count < 2` | `improve_strategy` |
| `insufficient` | 검증 실패이며 `retry_count >= 2` | `generate_insufficient_evidence_answer` |
| `regenerate` | `suggested_action == "REGENERATE"` | `generate_answer` |
| `retrieve_again` | 그 외의 개선 행동 | `retrieve_context` |

검증에 실패하면 먼저 `improve_strategy`에서 다음 단계에 적용할
구체적인 개선 지시를 생성합니다.

이후 `suggested_action`이 `REGENERATE`이면 기존 검색 근거를 유지한 채
답변만 다시 생성하고, 그 외에는 개선된 검색 지시를 반영해
약관과 소비자 보호 근거를 다시 검색합니다.

재시도 횟수가 2회에 도달한 뒤에도 검증을 통과하지 못하면
무한 반복을 방지하기 위해 근거 부족 안내 경로로 종료합니다.

## 6. 핵심 설계 결정
## 7. 문제 분석 및 개선 과정
## 8. 테스트 결과
## 9. 협업 및 통합
## 10. 회고
