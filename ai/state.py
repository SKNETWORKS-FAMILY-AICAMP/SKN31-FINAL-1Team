"""
state.py

Track A(문서 생성 파이프라인) 전체가 공유하는 State.
각 에이전트 노드는 이 State의 일부만 읽고, 자기 결과만 채워 반환한다.
(개별 에이전트 폴더의 schemas.py에 있는 입출력 모델과는 다른 개념 —
 여기 State는 "그래프 실행 중 흘러다니는 값"이고, schemas.py는 "그 값의
 유효성을 검증하는 계약"이다.)
"""

from typing import Any, Dict, List, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    # ---- 입력 ----
    meeting_id: str
    project_id: str

    # ---- A1-1 출력 ----
    structured_analysis: Dict[str, Any]

    # ---- A1-2 출력 / 반려 루프 ----
    plan: Dict[str, Any]
    plan_id: Optional[str]
    plan_rejection_reason: Optional[str]   # 반려 시 A1-2로 되돌아가며 채워짐

    # ---- A2-1 출력 / 반려 루프 ----
    requirement_doc: Dict[str, Any]
    requirement_rejection_reason: Optional[str]

    # ---- A2-2 출력 ----
    tasks: List[Dict[str, Any]]

    # ---- A2-3 출력 ----
    assignments: List[Dict[str, Any]]

    # ---- 공통 ----
    error: Optional[str]
