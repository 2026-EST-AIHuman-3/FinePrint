try:
    from .agent.workflow import graph
except ImportError:
    # ``python msh/test_agent.py`` 실행도 계속 지원한다.
    from agent.workflow import graph


initial_state = {
    "service_name": "넷플릭스",
    # "service_name": "코웨이", # PENALTY인 경우
    # "user_question": "해지했는데 또 결제됐어요. 환불받을 수 있나요?", # 자동 갱신
    # "user_question": "오늘 광주 날씨 알려 줘", # -> is_in_scope = False인 경우
    # "user_question": "제 계정이 갑자기 정지됐는데 정지 사유와 복구 조건을 알고 싶어요", # 계정 제한/정지 문제
    # "user_question": "구독 해지를 신청했는데 언제부터 이용이 종료되는지 모르겠어요.", # 해지 문제
    # "user_question": "결제 후 서비스를 이용하지 않았는데 환불받을 수 있나요?", # REFUND
    # "user_question": "같은 달에 요금이 두 번 결제됐어요. 어떻게 확인해야 하나요?", # PAYMENT
    # "user_question": "정수기 렌탈 계약을 중도 해지하려는데 위약금이 얼마나 발생하나요?", # PENALTY
    # "user_question": "구독료가 인상됐는데 사전 고지 없이 변경될 수 있나요?", # CONTRACT_CHANGE
    # "user_question": "제 계정이 갑자기 정지됐는데 정지 사유와 복구 조건을 알고 싶어요.", # ACCOUNT_RESTRICTION
    "user_question": "구독 서비스의 개인정보가 다른 회사에 제공되는지 알고 싶어요.", # 개인정보
    "retry_count": 0,
    "round_logs": [],
}

# for update in graph.stream(
#     initial_state,
#     stream_mode="updates",
# ):
#     print("\n==============================")
#     print(update)

result = graph.invoke(initial_state)

# print(result)

print("\n===== 검색된 약관 원문 =====")
print(result.get("terms_context", ""))

print("\n===== 검색된 소비자 보호 근거 =====")
print(result.get("consumer_protection_context", ""))

print("\n===== 최종 누적 로그 =====")
for log in result.get("round_logs", []):
    print(
        log["stage"],
        log.get("retry_count"),
        log.get("status", ""),
        log.get("suggested_action", ""),
    )

print("\n===== 최종 답변 =====")
print(result["final_answer"])

# png_data = graph.get_graph().draw_mermaid_png()

# with open("fineprint_workflow.png", "wb") as f:
#     f.write(png_data)
