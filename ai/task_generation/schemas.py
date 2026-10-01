"""
task_generation/schemas.py

컨텍스트 설계 요약
  - 입력: 요구사항정의서 출력(요구사항정의서 JSON), State Passing
  - 정적 참고자료: Depth 기준(Epic->Task->Subtask) + 3원칙, Prompt Template + Few-shot
  - 동적 조회: 없음
  - Tools: 없음
  - 출력: 업무 리스트 JSON (Epic 정보 포함, Subtask 중첩)
"""

from typing import Dict, List, Optional, Type

from pydantic import BaseModel, Field, create_model


class SubTask(BaseModel):
    subtask_id: str = Field(..., description="SUBTASK-{task순번}-{하위순번} 형식 (예: SUBTASK-001-1)")
    title: str
    description: str
    estimated_hours: float


class TaskItem(BaseModel):
    task_id: str = Field(..., description="TASK-{순번} 형식 (예: TASK-001)")
    epic_id: str = Field(..., description="소속 Epic 식별자 (EPIC-{순번} 형식, 예: EPIC-001)")
    epic_title: str = Field(..., description="소속 Epic 명")
    title: str
    description: str
    required_skills: List[str] = Field(
        default_factory=list,
        description="이 업무 수행에 필요한 기술 스택 (A2-3 담당자 배정 시 매칭 기준으로 사용됨)",
    )
    estimated_hours: float
    # 2026-09-11 (Phase 2): 일정 배치 품질을 위한 3개 필드 추가.
    # 값을 못 정하면 비워도 된다(코드가 기본값으로 처리) — 억지로 지어내지 않는다.
    dependency_task_ids: List[str] = Field(
        default_factory=list,
        description=(
            "이 업무보다 먼저 끝나야 하는 선행 업무의 task_id 목록(같은 응답 안의 값). "
            "예: 개발 업무는 설계 업무에 의존. 선행이 없으면 빈 리스트. "
            "일정 스케줄러가 이 순서대로 시작일을 미룬다."
        ),
    )
    risk_buffer_factor: Optional[float] = Field(
        default=None,
        description=(
            "estimated_hours에 곱할 여유 배율. 1.0=버퍼 없음. 불확실성이 클수록 크게: "
            "잘 정의된 CRUD ~1.2, 안 써본 기술/외부 연동 ~2.0. 못 정하면 null(코드가 기본값)."
        ),
    )
    feature_area: Optional[str] = Field(
        default=None,
        description="같은 기능 영역 묶음 라벨(예: '주문', '결제'). 같은 담당자에게 몰아주는 근거로 쓰인다. 못 정하면 null.",
    )
    difficulty: str = Field(..., description="상/중/하")
    difficulty_reason: str = Field(..., description="난이도 판단 근거 — 화면에 그대로 노출")
    source_req_id: str = Field(
        ...,
        description=(
            "어느 요구사항에서 파생됐는지 추적용. LLM이 채운 값은 참고용이고, "
            "실제로는 agent.py가 이 업무가 나온 요구사항 ID(딕셔너리 키)로 덮어써 확정한다."
        ),
    )
    subtasks: List[SubTask] = Field(
        default_factory=list,
        max_length=5,
        description="decomposition_principles 3원칙 미충족 시에만 생성. 충족 시 빈 리스트.",
    )


class TaskByRequirement(BaseModel):
    # 1차 시도용 응답 모델. 요구사항 ID를 키로 쓰되, 키 존재 자체를 스키마로
    # 강제하지는 않는다(느슨한 Dict). 처음부터 요구사항 전부를 필수로 걸면,
    # 그중 하나라도 안 맞을 때 Instructor가 응답 전체를 버리고 처음부터 다시
    # 생성시킨다 — 그러면 이미 맞게 나온 부분까지 같이 날아가서 "성공한 건
    # 두고 실패한 것만 재시도"가 안 된다. 그래서 1차는 느슨하게 받고, 빠진
    # 요구사항만 아래 build_requirement_keyed_model()로 좁혀서 재요청한다.
    by_requirement: Dict[str, List[TaskItem]] = Field(default_factory=dict)


class TaskList(BaseModel):
    # 1차 시도 + (필요시) 재시도 병합이 끝난 "최종" 결과 형태. 여기서는
    # 병합이 끝난 뒤 최소 1건이라도 남았는지 확인하는 마지막 안전장치로만
    # 쓴다 — 완전히 실패하면 ValidationError로 걸려서 task_generation_node가
    # 이를 에러로 반환한다.
    tasks: List[TaskItem] = Field(..., min_length=1)


class SkillRemapItem(BaseModel):
    """
    required_skills 어휘 재시도 응답 1건. task_id로 원본 업무를 지정하고,
    허용된 스킬 명단(available_skills) 안에서 골라 다시 채운 required_skills를
    돌려준다. 대응되는 값이 정말 없으면 원래 값을 그대로 둬도 된다 —
    지어내서 억지로 명단에 끼워 맞추지 않는다.
    """

    task_id: str
    required_skills: List[str] = Field(default_factory=list)


class SkillRemapBatch(BaseModel):
    """
    verify_skill_vocabulary()가 찾아낸, 허용 명단 밖 스킬을 쓴 업무들에 대한
    재요청 응답. 입력받은 task_id 전부에 대해 빠짐없이 반환해야 한다
    (agent.py의 _remap_skill_vocabulary 참고).
    """

    items: List[SkillRemapItem] = Field(default_factory=list)


def build_requirement_keyed_model(req_ids: List[str]) -> Type[BaseModel]:
    """요구사항 ID별로 필수 필드를 갖는 동적 스키마를 만든다.

    1차 시도에서 빠진 것으로 확인된 요구사항 ID만 좁혀서 재요청할 때 쓴다
    — 대상이 소수라 여기서는 전부 필수(min_length=1)로 걸어도 안전하다.
    (1차 시도처럼 요구사항 전체가 걸려 있는 게 아니라서, 여기서 실패해도
    "이미 맞은 것까지 날아가는" 손해가 없다.)
    """
    fields = {req_id: (List[TaskItem], Field(..., min_length=1)) for req_id in req_ids}
    return create_model("RequirementKeyedTasks", **fields)
