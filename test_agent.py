from agent.workflow import graph


initial_state = {
    "service_name": "넷플릭스",
    # "user_question": "해지했는데 또 결제됐어요. 환불받을 수 있나요?",
    # "user_question": "오늘 광주 날씨 알려 줘", # -> is_in_scope = False인 경우
    "user_question": "제 계정이 갑자기 정지됐는데 정지 사유와 복구 조건을 알고 싶어요",
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