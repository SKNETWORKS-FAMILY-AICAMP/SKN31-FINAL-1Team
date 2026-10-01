"""
assignment_ranking/schemas.py

2026-09-11 (Phase 3 item 10): WorkPackage 분할 판단 에이전트의 입출력.

이 에이전트는 "누구에게 배정할지"는 건드리지 않는다 — 그건 assignee_recommend의
결정적 스케줄러 몫이다. 여기서는 각 기능 묶음(WorkPackage)을 한 담당자에게
통째로 맡길지, 나눠야 할지 "split 여부"만 판단한다("절충" 방식 — 2026-09-11 결정).
"""

from typing import List

from pydantic import BaseModel, Field


class PackageSplitDecision(BaseModel):
    package_id: str
    split: bool = Field(
        False, description="이 기능 묶음을 여러 담당자에게 나눠 맡기는 게 나은가"
    )
    reason: str = Field(
        "", description="split 판단 근거 한 문장 — PM에게 그대로 노출된다"
    )
    unit_groups: List[List[str]] = Field(
        default_factory=list,
        description=(
            "split=true일 때만. 각 하위 그룹에 들어갈 unit_id 목록. 패키지의 모든 "
            "unit이 정확히 한 그룹에 들어가야 한다. 어느 unit끼리 묶일지 확신이 서면 "
            "채우고, 애매하면 비워라 — 코드가 요구사항/역할 기준으로 자동 분할한다."
        ),
    )


class PackageSplitBatch(BaseModel):
    """여러 패키지의 분할 판단을 한 번의 LLM 호출로 받는다."""

    decisions: List[PackageSplitDecision] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2026-09-11: 후보 질적 적합도 — "코드가 이미 스킬로 좁힌 소수 후보"의 경력기술서
# 원문·자격증·숙련도 내용을 이 업무 설명과 직접 대조해서 판단한다. 누구에게
# 배정할지(최종 선택)·부하 누적·용량 상한은 여전히 코드(schedule_assignments)가
# 한다 — 이 점수는 _fit_score의 한 항목(경력·자격증)으로만 들어간다.
# ---------------------------------------------------------------------------
class CandidateFitScore(BaseModel):
    employee_id: str
    fit_score: float = Field(
        ..., ge=0.0, le=1.0,
        description=(
            "이 후보가 이 업무에 얼마나 질적으로 맞는지 — 경력기술서 원문·자격증·"
            "스킬 숙련도의 내용을 이 업무 설명과 직접 비교해서 판단하라. 개수가 "
            "아니라 내용의 관련성을 본다. 0=관련 경험 전혀 없음, 1=이 업무를 위해 "
            "준비된 것 같은 정도."
        ),
    )
    reason: str = Field(
        ..., description="왜 이 점수인지 한 문장 — 경력기술서의 구체적 내용을 인용해서 서술"
    )


class UnitCandidateFit(BaseModel):
    unit_id: str
    candidates: List[CandidateFitScore] = Field(default_factory=list)


class CandidateFitBatch(BaseModel):
    """여러 업무의 후보 적합도 판단을 한 번의 LLM 호출로 받는다. 입력받은 unit_id
    전부와, 각 unit에 딸려 보낸 후보 전원에 대해 빠짐없이 점수를 반환해야 한다."""

    units: List[UnitCandidateFit] = Field(default_factory=list)
