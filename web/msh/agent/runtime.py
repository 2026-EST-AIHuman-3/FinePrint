"""FastAPI 같은 비동기 애플리케이션에서 FinePrint 그래프를 실행하는 경계 계층."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Protocol


class AgentGraph(Protocol):
    """LangGraph compiled graph에서 사용하는 최소 실행 인터페이스."""

    def invoke(self, input: dict[str, Any]) -> Mapping[str, Any]: ...


def build_initial_state(
    service_name: str,
    user_question: str,
    policy_urls: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """API 입력을 FinePrintState의 초기 상태로 변환한다."""

    return {
        "service_name": service_name.strip(),
        "user_question": user_question.strip(),
        "policy_urls": dict(policy_urls or {}),
        "retry_count": 0,
        "round_logs": [],
        "improvement_instruction": "",
    }


def _validate_result(result: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    if not isinstance(normalized.get("final_answer"), Mapping):
        raise RuntimeError("Agent가 final_answer를 반환하지 않았습니다.")
    normalized["final_answer"] = dict(normalized["final_answer"])
    return normalized


async def run_agent_workflow(
    agent_graph: AgentGraph,
    *,
    service_name: str,
    user_question: str,
    policy_urls: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """LangGraph를 실행하되 FastAPI 이벤트 루프를 막지 않는다.

    최신 LangGraph의 ``ainvoke``가 있으면 그대로 사용하고, 동기 실행기만
    주입된 테스트/대체 구현은 작업 스레드에서 실행한다.
    """

    initial_state = build_initial_state(
        service_name=service_name,
        user_question=user_question,
        policy_urls=policy_urls,
    )

    async_invoke = getattr(agent_graph, "ainvoke", None)
    if callable(async_invoke):
        result = await async_invoke(initial_state)
    else:
        result = await asyncio.to_thread(agent_graph.invoke, initial_state)

    if not isinstance(result, Mapping):
        raise RuntimeError("Agent 실행 결과 형식이 올바르지 않습니다.")
    return _validate_result(result)
