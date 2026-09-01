"""
a2_3_assignee_recommend/rule_filter.py

우선순위(요구사항 priority 상속) 순으로 정렬한 배정 단위를, 기술이 맞고 아직
여유가 있는 최적 담당자에게 순차 배정하는 그리디 스케줄러.
"누구에게 배정할지"는 전부 여기(코드)가 확정하고, LLM에게는 "왜 적합한지"
서술만 맡긴다 (agent.py, prompt_builder.py 참고).

배정 단위 정의 — decomposition_principles 3원칙에 따라, Task에 subtasks가 있으면
그 Task 자체는 담당자 1인에게 배정 가능한 단위가 아니다. 그래서 배정 대상은
"subtasks가 없는 Task 자신" 또는 "subtasks가 있는 Task의 각 Subtask"이다.

가용시간 계산 방식 — User 테이블에 "총 가용시간" 필드를 별도로 두지 않는다.
그 값은 배정할 때마다 갱신해야 하는 중복 데이터가 되기 때문이다. 대신
task.estimated_hours를 assignee_id 기준으로 합산한 "현재 부하"(get_current_workload,
agent.py 참고)를 실행 시점에 SQL로 조회해서 쓴다.

상한선 계산 — "1일 8시간 · 주 5일 근무 = 주 40시간"을 전제로, 프로젝트 기간 안의
실제 평일(월~금) 수를 세어 시간으로 환산한다(calculate_max_hours_per_assignee).
달력 일수를 그냥 7로 나누는 평균 근사는 쓰지 않는다 — 예를 들어 월~금 5일짜리
프로젝트를 "달력일수÷7×40"으로 계산하면 40시간이 아니라 약 28.6시간이 나와,
시작/종료 요일에 따라 오차가 크다. 평일을 직접 세면 이 오차가 없다.
project.start_date/end_date는 이미 있는 컬럼이라 이 계산 자체엔 DB 조회가
필요 없고, 두 날짜 값만 받으면 된다. 공휴일은 반영하지 않는다(별도 공휴일
데이터가 필요해 지금 범위 밖 — 필요해지면 팀과 상의).
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Union

_PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2, None: 3}

# TODO(팀 합의 필요): 담당자 1인이 근무일 하루에 이 업무에 쓸 수 있는 시간.
# DB 필드가 아니라 코드 상수 — calculate_max_hours_per_assignee()가 프로젝트
# 기간 내 평일 수와 곱해 실제 상한을 계산하는 데 쓴다.
DAILY_HOURS_PER_ASSIGNEE = 8.0


def _to_date(value: Union[str, date]) -> date:
    return value if isinstance(value, date) else datetime.strptime(value, "%Y-%m-%d").date()


def calculate_max_hours_per_assignee(
    project_start_date: Union[str, date],
    project_end_date: Union[str, date],
    hours_per_workday: float = DAILY_HOURS_PER_ASSIGNEE,
) -> float:
    """
    프로젝트 기간(시작일~종료일, 양끝 포함) 안의 평일(월~금) 수를 세어
    하루 근무시간을 곱한다. 문자열("YYYY-MM-DD")과 date 객체 둘 다 받는다 —
    State에 JSON으로 실려오면 문자열일 수 있어서다.
    """
    start = _to_date(project_start_date)
    end = _to_date(project_end_date)
    if end <= start:
        raise ValueError(
            f"project_end_date({end})는 project_start_date({start})보다 뒤여야 합니다"
        )

    workdays = 0
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=월요일 ... 4=금요일, 5=토, 6=일은 제외
            workdays += 1
        current += timedelta(days=1)

    return round(workdays * hours_per_workday, 1)


def flatten_assignable_units(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Task/Subtask 목록에서 실제로 배정 가능한 최소 단위만 뽑아낸다."""
    units = []
    for task in tasks:
        subtasks = task.get("subtasks") or []
        if not subtasks:
            units.append(
                {
                    "unit_id": task["task_id"],
                    "parent_task_id": None,
                    "title": task["title"],
                    "description": task["description"],
                    "required_skills": task.get("required_skills", []),
                    "estimated_hours": task["estimated_hours"],
                    "source_req_id": task["source_req_id"],
                }
            )
        else:
            for sub in subtasks:
                units.append(
                    {
                        "unit_id": sub["subtask_id"],
                        "parent_task_id": task["task_id"],
                        "title": sub["title"],
                        "description": sub["description"],
                        # Subtask 자체엔 required_skills가 없어 소속 Task 값을 상속한다.
                        "required_skills": task.get("required_skills", []),
                        "estimated_hours": sub["estimated_hours"],
                        "source_req_id": task["source_req_id"],
                    }
                )
    return units


def sort_units_by_priority(
    units: List[Dict[str, Any]], priority_by_req_id: Dict[str, Optional[str]]
) -> List[Dict[str, Any]]:
    """
    우선순위(요구사항 priority 상속) 순으로 정렬한다. 같은 우선순위 안에서는
    estimated_hours 내림차순 — 큰 업무를 먼저 배정해, 이후 작은 업무가 자투리
    가용시간에도 들어갈 여지를 남기는 그리디 휴리스틱이다. priority가 없는
    (검토대기) 요구사항에서 파생된 업무는 맨 뒤로 보낸다.
    """

    def key(u: Dict[str, Any]):
        prio = priority_by_req_id.get(u["source_req_id"])
        return (_PRIORITY_RANK.get(prio, 3), -u["estimated_hours"], u["unit_id"])

    return sorted(units, key=key)


def _fit_score(
    unit: Dict[str, Any],
    member: Dict[str, Any],
    matched_skills: set,
    remaining_ratio: float,
) -> float:
    """
    가용시간은 schedule_assignments()의 상한 컷오프("배정 가능/불가능")에서 이미
    한 번 걸러지지만, 그것만으로는 부족하다 — 통과한 후보들 사이에서 순위를
    스킬·경험·자격증만으로 매기면, 여유가 얼마나 남았는지와 무관하게 항상 같은
    사람이 이겨서 그 사람에게 계속 몰릴 수 있다. 이건 애초에 이 알고리즘을 만든
    목적("여러 명에게 고르게 분배")과 어긋난다. 그래서 남는 여유(remaining_ratio)도
    작은 가중치로 점수에 넣어, 역량이 비슷하면 여유 있는 쪽으로 자연스럽게 기울게
    한다 — "정확히 동점일 때만" 적용하는 규칙보다 이렇게 상시 반영하는 쪽이 더
    안정적이다(부동소수점 점수가 정확히 같아지는 경우 자체가 드물다).

    자격증(certifications)은 주 기준이 아니라 "가산점" — 기술·경험이 비슷한
    후보끼리 갈릴 때 차이를 만드는 보조 요소로 가중치를 작게 둔다.

    remaining_ratio: 이 업무까지 배정했다고 가정했을 때, 상한 대비 남는 여유
    비율(0~1). 1에 가까울수록 여유가 많고, 0이면 상한을 딱 채운다.
    """
    required = set(unit.get("required_skills", []))
    skill_ratio = len(matched_skills) / len(required) if required else 1.0
    similar_count = len(member.get("past_similar_tasks", []))
    cert_count = len(member.get("certifications", []))
    return round(
        0.45 * skill_ratio
        + 0.20 * min(similar_count / 3, 1)
        + 0.15 * min(cert_count / 2, 1)  # 자격증 가산점 — 2개부터 만점
        + 0.20 * remaining_ratio,  # 여유 많을수록 가점 — 특정 인원 쏠림 방지
        3,
    )


def schedule_assignments(
    units: List[Dict[str, Any]],
    members: List[Dict[str, Any]],
    current_workload: Dict[str, float],
    max_hours_per_assignee: float,
) -> List[Dict[str, Any]]:
    """
    우선순위 정렬된 units를 순서대로 순회하며, 요구 기술을 만족하고 아직
    여유가 있는 담당자 중 최적 후보(_fit_score 최댓값)에게 배정하고,
    그 즉시 해당 담당자의 부하를 늘린다.

    Args:
        units: flatten_assignable_units() + sort_units_by_priority() 결과
        members: [{"employee_id", "skills": [...], "past_similar_tasks": [...]}, ...]
                 (assignee_mapping 에이전트의 EmployeeFitnessProfile 출력)
        current_workload: {employee_id: 이미 배정된 미완료 업무의 estimated_hours 합}
                 — task 테이블에서 SQL로 조회한 값 (agent.py의 get_current_workload 참고).
                 이 함수 안에서 배정이 늘어날 때마다 이 값에 누적해서 반영한다.
        max_hours_per_assignee: calculate_max_hours_per_assignee()로 프로젝트
                 기간에 맞춰 계산한 값. 프로젝트마다 다르므로 기본값을 두지 않는다
                 — 호출부(agent.py)가 항상 명시적으로 계산해서 넘겨야 한다.

    Returns:
        unit마다 배정 결과 dict. employee_id가 None이면 보류(review_required).
    """
    workload = dict(current_workload)  # 원본 훼손 방지용 복사, 이 배치 안에서 누적 증가시킨다
    member_by_id = {m["employee_id"]: m for m in members}

    results = []
    for unit in units:
        required = set(unit.get("required_skills", []))
        best_id: Optional[str] = None
        best_matched: set = set()
        best_score = -1.0

        for m in members:
            emp_id = m["employee_id"]
            projected = workload.get(emp_id, 0.0) + unit["estimated_hours"]
            if projected > max_hours_per_assignee:
                continue  # 이 업무까지 더하면 상한을 넘기는 사람은 후보에서 제외
            matched = required & set(m.get("skills", []))
            if required and not matched:
                continue  # 요구 기술과 하나도 안 겹치면 제외
            remaining_ratio = (
                1 - (projected / max_hours_per_assignee) if max_hours_per_assignee > 0 else 0.0
            )
            score = _fit_score(unit, m, matched, remaining_ratio)
            if score > best_score:
                best_score, best_id, best_matched = score, emp_id, matched

        if best_id is None:
            results.append({"unit": unit, "employee_id": None})
            continue

        workload[best_id] = workload.get(best_id, 0.0) + unit["estimated_hours"]
        m = member_by_id[best_id]
        certifications = m.get("certifications", [])
        skill_text = (
            f"{'/'.join(sorted(best_matched))} 보유, 관련 업무 {len(m.get('past_similar_tasks', []))}건 수행"
            if best_matched
            else f"관련 업무 {len(m.get('past_similar_tasks', []))}건 수행"
        )
        if certifications:
            skill_text += f", 관련 자격증 {'/'.join(certifications)} 보유"
        results.append(
            {
                "unit": unit,
                "employee_id": best_id,
                "score": best_score,
                "skill_match": skill_text,
                "workload": f"이번 배정 포함 현재 부하 {workload[best_id]:.1f}시간 (상한 {max_hours_per_assignee:.1f}시간)",
                "similar_experience": f"유사 업무 완료 이력 {len(m.get('past_similar_tasks', []))}건",
            }
        )

    return results
