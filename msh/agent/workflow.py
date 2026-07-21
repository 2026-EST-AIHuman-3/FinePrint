from langgraph.graph import StateGraph, START, END

from .state import FinePrintState
from .nodes import (
    classify_intent,
    retrieve_context,
    generate_answer,
    verify_answer,
    improve_strategy,
    generate_final_answer,
    generate_insufficient_evidence_answer,
    generate_out_of_scope_answer
)

# 분기 함수 - 답변 재생성인지 근거 재검색인지 여부
def route_improvement(state: FinePrintState):
    action = state["suggested_action"]

    if action == "REGENERATE":
        return "regenerate"

    return "retrieve_again"

# 분기 함수! - out-of-scope 인지 아닌지 여부
def route_scope(state: FinePrintState):
    if state["is_in_scope"]:
        return "in_scope"

    return "out_of_scope"

# 무한 루프 방지!
def route_verification(state: FinePrintState):
    status = state["verification_status"]
    retry_count = state["retry_count"]

    if status == "PASS":
        return "pass"

    if retry_count >= 2:
        return "insufficient"

    return "fail"

builder = StateGraph(FinePrintState)

builder.add_node("classify_intent", classify_intent)
builder.add_node("retrieve_context", retrieve_context)
builder.add_node("generate_answer", generate_answer)
builder.add_node("verify_answer", verify_answer)
builder.add_node("improve_strategy", improve_strategy)
builder.add_node("generate_final_answer", generate_final_answer)
builder.add_node(
    "generate_insufficient_evidence_answer",
    generate_insufficient_evidence_answer,
)
builder.add_node(
    "generate_out_of_scope_answer",
    generate_out_of_scope_answer,
)


builder.add_edge(START, "classify_intent")

builder.add_conditional_edges(
    "classify_intent",
    route_scope,
    {
        "in_scope": "retrieve_context",
        "out_of_scope": "generate_out_of_scope_answer",
    },
)

builder.add_edge("retrieve_context", "generate_answer")
builder.add_edge("generate_answer", "verify_answer")

builder.add_conditional_edges(
    "verify_answer",
    route_verification,
    {
        "pass": "generate_final_answer",
        "fail": "improve_strategy",
        "insufficient": "generate_insufficient_evidence_answer",
    },
)

builder.add_conditional_edges(
    "improve_strategy",
    route_improvement,
    {
        "retrieve_again": "retrieve_context",
        "regenerate": "generate_answer",
    },
)

builder.add_edge("generate_final_answer", END)
builder.add_edge(
    "generate_insufficient_evidence_answer",
    END,
)
builder.add_edge(
    "generate_out_of_scope_answer",
    END,
)

graph = builder.compile()
