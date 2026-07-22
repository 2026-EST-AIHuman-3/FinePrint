from __future__ import annotations

import unittest

from fastapi import HTTPException


class UpstreamError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


class AgentHttpExceptionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # api import는 임베딩 모델과 그래프를 초기화하므로 의존성이 설치된
        # 통합 환경에서만 이 테스트 모듈을 실행한다.
        from api import _agent_http_exception

        cls.convert = staticmethod(_agent_http_exception)

    def test_authentication_error_is_sanitized(self):
        error = self.convert(UpstreamError(401))

        self.assertIsInstance(error, HTTPException)
        self.assertEqual(error.status_code, 502)
        self.assertEqual(error.detail["code"], "OPENAI_AUTH_FAILED")
        self.assertNotIn("sk-", str(error.detail))

    def test_rate_limit_error_is_service_unavailable(self):
        error = self.convert(UpstreamError(429))

        self.assertEqual(error.status_code, 503)
        self.assertEqual(error.detail["code"], "OPENAI_RATE_LIMITED")

    def test_unknown_error_hides_original_message(self):
        error = self.convert(Exception("secret backend detail"))

        self.assertEqual(error.status_code, 500)
        self.assertNotIn("secret backend detail", str(error.detail))


if __name__ == "__main__":
    unittest.main()
