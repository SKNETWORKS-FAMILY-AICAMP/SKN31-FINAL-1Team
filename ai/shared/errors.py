"""
shared/errors.py

AI 노드 실행 실패를 표현하는 공용 예외.

배경: 지금까지 meeting_analysis/plan_draft는 LLM 호출 실패를 그대로
위로 흘려보냈다. 호출부(backend/meetings/views.py)는 이걸 하나의
`except Exception`으로 뭉뚱그려 잡아서, 원인이 무엇이든 항상 같은
안내문("AI 기획서 생성 중 오류가 발생했습니다")을 돌려주고 있었다.

노드마다 각자 다른 예외를 던지면 호출부가 원인별로 다른 안내 메시지를
주기 어렵다. cause_code로 원인을 구분해서 전달하면, 호출부는 이 코드만
보고 사용자 메시지를 고르면 된다 — requirement_draft 쪽(노드③)이
ValueError/RuntimeError 두 가지로 구분해 쓰고 있는 것과 같은 목적이지만,
여기서는 노드가 늘어나도 새 예외 클래스를 만들 필요 없이 cause_code
문자열만 추가하면 되도록 통합했다.

cause_code 종류:
  - LLM_RETRY_EXHAUSTED : Instructor가 스키마 검증에 최종 실패
                          (초기 시도 + MAX_RETRIES회 모두 소진)
  - LLM_API_ERROR       : OpenAI API 호출 자체가 실패
                          (네트워크·인증·요청 한도·타임아웃 등)
  - CONFIG_ERROR        : OPENAI_API_KEY 등 설정 누락
  - UNKNOWN             : 위 셋에 해당하지 않는 그 외 오류

호출부(백엔드)가 할 일은 아직 남아 있다 — 지금은 ai/ 쪽에서 로그를
남기고 이 예외를 던지는 부분까지만이고, backend/meetings/views.py가
cause_code별로 다른 HTTP 응답 메시지를 고르는 부분은 별도 작업이다
(backend/requirements/views.py의 ValueError/Exception 분기 패턴 참고).
"""

from __future__ import annotations


class NodeGenerationError(Exception):
    """AI 노드(meeting_analysis/plan_draft 등) 실행 중 발생한 실패.

    Attributes:
        node: 실패한 노드 이름 (예: "meeting_analysis", "plan_draft")
        cause_code: 위 모듈 docstring의 cause_code 중 하나
        original: 원래 발생한 예외 (로그·디버깅용으로 보존)
    """

    def __init__(
        self,
        message: str,
        *,
        cause_code: str,
        node: str,
        original: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.cause_code = cause_code
        self.node = node
        self.original = original
