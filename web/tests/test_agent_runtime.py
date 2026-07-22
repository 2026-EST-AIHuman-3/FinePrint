from __future__ import annotations

import asyncio
import unittest

from msh.agent.runtime import build_initial_state, run_agent_workflow


class AsyncFakeGraph:
    def __init__(self) -> None:
        self.received_state = None

    async def ainvoke(self, state):
        self.received_state = state
        return {
            **state,
            "primary_intent": "REFUND",
            "is_in_scope": True,
            "final_answer": {
                "problem_type": "환불 문제",
                "simple_explanation": "테스트 답변",
            },
        }


class SyncFakeGraph:
    def invoke(self, state):
        return {**state, "final_answer": {"message": "범위 밖 질문"}}


class InvalidFakeGraph:
    async def ainvoke(self, state):
        return {**state, "draft_answer": "최종 답변 없음"}


class AgentRuntimeTest(unittest.TestCase):
    def test_build_initial_state(self):
        state = build_initial_state(
            " 넷플릭스 ",
            " 환불 가능한가요? ",
            {"terms": "https://example.com/terms"},
        )

        self.assertEqual(state["service_name"], "넷플릭스")
        self.assertEqual(state["user_question"], "환불 가능한가요?")
        self.assertEqual(state["retry_count"], 0)
        self.assertEqual(state["round_logs"], [])
        self.assertEqual(
            state["policy_urls"],
            {"terms": "https://example.com/terms"},
        )

    def test_async_graph_is_used(self):
        fake = AsyncFakeGraph()
        result = asyncio.run(
            run_agent_workflow(
                fake,
                service_name="넷플릭스",
                user_question="환불 가능한가요?",
            )
        )

        self.assertEqual(result["final_answer"]["problem_type"], "환불 문제")
        self.assertEqual(fake.received_state["improvement_instruction"], "")

    def test_sync_graph_falls_back_to_worker_thread(self):
        result = asyncio.run(
            run_agent_workflow(
                SyncFakeGraph(),
                service_name="넷플릭스",
                user_question="오늘 날씨는?",
            )
        )

        self.assertEqual(result["final_answer"]["message"], "범위 밖 질문")

    def test_missing_final_answer_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "final_answer"):
            asyncio.run(
                run_agent_workflow(
                    InvalidFakeGraph(),
                    service_name="넷플릭스",
                    user_question="환불 가능한가요?",
                )
            )


if __name__ == "__main__":
    unittest.main()
