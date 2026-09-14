"""
ai/team_sizing.py

프로젝트 실제 팀 배정 "전"에, 업무 목록(A2-2 출력)만으로 필요 인원을 추정하는
순수 계산 모듈. LLM을 쓰지 않고 사원 정보도 필요 없다 — assignee_mapping/
assignee_recommend와는 완전히 독립적이며, task_generation 직후 아무 때나
실행 가능하다.

이 모듈이 별도로 존재하는 이유 (2026-09-01 팀 논의에서 결정):
  - 입력이 다르다: 이건 tasks + 프로젝트 기간만 필요하고, assignee_mapping은
    사원 개개인의 career_history_text가 필요하다.
  - 의미 있는 실행 시점이 다르다: 이건 실제 팀이 정해지기 "전"에 PM이 팀 구성을
    계획할 때 참고하는 값이고, assignee_mapping/assignee_recommend는 팀이
    정해진 "후"에만 실행 가능하다. 한 노드로 묶으면 이 순서를 표현할 수 없다.
  - 순수 계산이라 LLM 노드에 얹으면 실패 격리·테스트 용이성을 잃는다
    ("코드는 결정, LLM은 서술만" 원칙 — assignee_recommend/rule_filter.py 참고).

역할 라벨은 새로 이름을 짓지 않고 회사 실제 CommonCode 값을 그대로 쓴다
(USER_JOB_ROLE 그룹, backend/datadump.json 참고: BACKEND/FRONTEND/FULLSTACK/
DATA_ENGINEER/DEVOPS/PROJECT_MANAGER/QA_ENGINEER/UIUX_DESIGNER). 그래야 이
계산 결과("BACKEND 3명 필요")가 나중에 실제 사원 수(job_role_code_id='BACKEND')와
직접 비교 가능하다.

의도적으로 SKILL_ROLE_MAP에서 뺀 것:
  - PROJECT_MANAGER: 요구사항정의서 자체가 "개발~배포" 범위만 다뤄, 업무의
    required_skills로는 절대 안 잡힌다. PM 인원은 팀 별도 정책(예: 프로젝트당
    고정 인원)으로 정할 문제라 이 계산 밖이다.
  - FULLSTACK: 업무의 종류가 아니라 사람의 속성이다. 업무 -> 역할 계산인 이
    모듈엔 대응하는 스킬이 없다. "필요인원 vs 실제 보유인력" 비교(사원 데이터가
    필요한 단계, 아직 미착수)에서나 의미가 있다.
  - QA_ENGINEER: pytest 같은 테스트 스킬을 여기로 보낼지, 개발 역할에 그대로
    남길지(=개발자가 자기 코드 테스트도 한다고 볼지) 팀 컨벤션이 아직 없어서
    비워뒀다. 정해지면 SKILL_ROLE_MAP에 추가.

한 업무의 required_skills가 여러 역할에 걸치면(예: ["Django", "MySQL"]),
다수결로 한 역할에 몰아주지 않고 estimated_hours를 매칭된 역할 수만큼
비례 분배한다.

주의 — 이 값은 "확정 인원"이 아니라 참고용 추정치다. 역할별로 올림(ceil)
계산을 하기 때문에, 역할을 잘게 나눌수록 실제 필요 총량보다 과대추정된다
(예: 4개 역할이 각각 0.3명 분량이면, 실제로는 1.2명 분량인데 4명으로 계산됨).

프론트/백엔드 연동(화면에 이 값을 어떻게 보여줄지, API 엔드포인트를 어디 둘지)은
프론트·백엔드 담당자와 별도 협의가 필요해 이 모듈에선 다루지 않는다 — 여기선
순수 계산 함수만 제공한다 (2026-09-01 결정, 연동은 추후 작업).
"""

import math
from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional, Union

from assignee_recommend.rule_filter import calculate_max_hours_per_assignee, flatten_assignable_units

# 2026-09-11: skill -> role 는 이제 회사 인력에서 도출한다(build_skill_role_map).
# 아래 표는 인력 데이터가 없을 때(cold start)만 쓰는 씨앗이지, 유일한 소스가 아니다.
# work_package / assignment_ranking 의 분할 로직도 이 표를 참조하므로 유지한다.
SKILL_ROLE_MAP: Dict[str, str] = {
    "React": "FRONTEND",
    "Vue": "FRONTEND",
    "Redux": "FRONTEND",
    "HTML": "FRONTEND",
    "CSS": "FRONTEND",
    "Django": "BACKEND",
    "Spring": "BACKEND",
    "Node.js": "BACKEND",
    "REST API": "BACKEND",
    "REST API 설계": "BACKEND",
    "MySQL": "DATA_ENGINEER",
    "PostgreSQL": "DATA_ENGINEER",
    "ERD 설계": "DATA_ENGINEER",
    "Docker": "DEVOPS",
    "AWS": "DEVOPS",
    "CI/CD": "DEVOPS",
    "Kubernetes": "DEVOPS",
    "Figma": "UIUX_DESIGNER",
}
UNMAPPED_ROLE = "미분류"

# skill -> role 도출에서 제외하는 직무. PROJECT_MANAGER는 요구사항 스킬로 안 잡히고,
# FULLSTACK은 "업무 종류"가 아니라 "사람 속성"이라 이 계산(업무->역할)의 대상이 아니다
# (모듈 상단 주석 참고). QA_ENGINEER는 포함한다 — 도출 방식에서는 그 사람들이
# 가진 테스트 스킬이 자연히 QA로 잡히기 때문(하드코딩으로는 못 하던 것).
_NON_COUNTED_ROLES = {"PROJECT_MANAGER", "FULLSTACK"}

# 도출된 skill->role 분포에서 이 비중 미만인 역할은 버린다. 안 그러면 한 스킬이
# 3~4개 역할에 걸쳐, 역할마다 headcount가 올림(ceil)돼 필요 인원이 크게 과대추정된다.
_MIN_ROLE_WEIGHT = 0.15

# cold start 씨앗: 인력 데이터가 없을 때만 쓴다. {skill: {role: 1.0}} 형태로 변환.
_SEED_SKILL_ROLE_MAP: Dict[str, Dict[str, float]] = {
    skill: {role: 1.0} for skill, role in SKILL_ROLE_MAP.items()
}


def build_skill_role_map(employee_profiles: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """
    재직 사원의 (job_role, skills)에서 skill -> {role: weight} 를 도출한다.
    weight = 그 스킬 보유자 중 해당 역할이 차지하는 비율(합 1.0).

    2026-09-11 신설 — 하드코딩 SKILL_ROLE_MAP 대체. 새 스킬이 생기고 그 스킬을
    가진 사람이 입사하면 매핑이 저절로 채워진다. 아무도 안 가진 스킬은 여기 없고,
    그건 "우리 팀에 그 역량이 없다"는 신호로 estimate_team_size에서 UNMAPPED_ROLE로
    집계된다.

    Args:
        employee_profiles: planning_context.build_employee_profiles() 출력 형태
            ({"is_active", "job_role", "skills", ...} dict 목록).
    """
    role_counts: Dict[str, Counter] = {}
    for p in employee_profiles:
        if not p.get("is_active"):
            continue
        role = p.get("job_role")
        if not role or role in _NON_COUNTED_ROLES:
            continue
        for skill in p.get("skills") or []:
            role_counts.setdefault(skill, Counter())[role] += 1

    result: Dict[str, Dict[str, float]] = {}
    for skill, counts in role_counts.items():
        total = sum(counts.values())
        dist = {r: c / total for r, c in counts.items() if c / total >= _MIN_ROLE_WEIGHT}
        if not dist:  # 여러 역할에 고르게 흩어져 전부 threshold 미만이면 최다 역할만
            dist = {counts.most_common(1)[0][0]: 1.0}
        norm = sum(dist.values())
        result[skill] = {r: round(w / norm, 4) for r, w in dist.items()}
    return result


def _distribute_unit_hours(
    unit: Dict[str, Any], skill_role_map: Dict[str, Dict[str, float]]
) -> Dict[str, float]:
    """unit의 estimated_hours를 역할별로 나눈다. required_skills에 균등 분배한 뒤
    각 스킬을 skill_role_map의 {role: weight}로 배분한다. 매핑에 없는 스킬 또는
    required_skills 자체가 비면 UNMAPPED_ROLE로."""
    hours = unit["estimated_hours"]
    skills = unit.get("required_skills") or []
    out: Dict[str, float] = {}
    if not skills:
        out[UNMAPPED_ROLE] = hours
        return out
    per_skill = hours / len(skills)
    for s in skills:
        dist = skill_role_map.get(s)
        if not dist:
            out[UNMAPPED_ROLE] = out.get(UNMAPPED_ROLE, 0.0) + per_skill
            continue
        for role, weight in dist.items():
            out[role] = out.get(role, 0.0) + per_skill * weight
    return out


def estimate_team_size(
    tasks: List[Dict[str, Any]],
    project_start_date: Union[str, date],
    project_end_date: Union[str, date],
    skill_role_map: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """
    업무 목록과 프로젝트 기간으로 역할별/전체 필요인원을 추정한다.

    Args:
        tasks: task_generation_node 출력의 state["tasks"] 그대로.
        project_start_date / project_end_date: "YYYY-MM-DD" 문자열 또는 date.
        skill_role_map: build_skill_role_map() 출력. 없으면 _SEED_SKILL_ROLE_MAP
            (cold start 씨앗)을 쓴다 — 호출부(services)는 항상 도출된 맵을 넘긴다.

    Returns:
        {"team_size_estimate": {"total_headcount", "by_role", "assumptions"}}
        by_role은 [{"role", "estimated_hours", "headcount"}, ...], estimated_hours 내림차순.
        role == UNMAPPED_ROLE 인 항목이 있으면 "그 스킬을 가진 인력이 우리 팀에 없다"는 뜻.
    """
    max_hours = calculate_max_hours_per_assignee(project_start_date, project_end_date)
    units = flatten_assignable_units(tasks)
    if skill_role_map is None:
        skill_role_map = _SEED_SKILL_ROLE_MAP

    hours_by_role: Dict[str, float] = {}
    for unit in units:
        for role, h in _distribute_unit_hours(unit, skill_role_map).items():
            hours_by_role[role] = hours_by_role.get(role, 0.0) + h

    by_role = [
        {
            "role": role,
            "estimated_hours": round(hours, 1),
            "headcount": math.ceil(hours / max_hours) if max_hours > 0 else 0,
        }
        for role, hours in sorted(hours_by_role.items(), key=lambda kv: -kv[1])
    ]
    total_headcount = sum(r["headcount"] for r in by_role)

    return {
        "team_size_estimate": {
            "total_headcount": total_headcount,
            "by_role": by_role,
            "assumptions": {"max_hours_per_assignee": max_hours},
        }
    }


# project_scale.agent.assess_project_complexity()가 판단한 복잡도 등급(하/중/상)에
# 곱할 버퍼 비율. 등급 선택은 LLM이 하지만, 등급->숫자 변환은 이 고정 매핑표와
# apply_complexity_buffer()(코드)가 한다 — "코드가 결정, LLM은 서술만" 원칙
# (task_generation의 difficulty->difficulty_code 변환과 동일한 패턴).
COMPLEXITY_BUFFER: Dict[str, float] = {"하": 0.0, "중": 0.15, "상": 0.30}


def apply_complexity_buffer(team_size_estimate: Dict[str, Any], complexity: str) -> Dict[str, Any]:
    """
    estimate_team_size()가 반환한 dict를 그대로 받아, 역할별 headcount에
    COMPLEXITY_BUFFER의 비율을 곱해 올림 처리한 새 dict를 반환한다(원본은
    훼손하지 않음). total_headcount도 보정된 값 기준으로 다시 합산한다.

    estimated_hours 자체는 손대지 않는다 — 그건 task_generation이 계산한
    실측치라 복잡도 판단과 무관하게 그대로 둔다. 보정 대상은 어디까지나
    "team_sizing이 놓치는 정성적 리스크를 반영한 인원 여유분"인 headcount뿐이다.
    """
    buffer = COMPLEXITY_BUFFER.get(complexity)
    if buffer is None:
        raise ValueError(f"알 수 없는 복잡도 값: {complexity!r} (허용값: {sorted(COMPLEXITY_BUFFER)})")

    estimate = team_size_estimate["team_size_estimate"]
    adjusted_by_role = []
    for r in estimate["by_role"]:
        adjusted = dict(r)
        adjusted["headcount"] = math.ceil(r["headcount"] * (1 + buffer))
        adjusted_by_role.append(adjusted)

    return {
        "team_size_estimate": {
            "total_headcount": sum(r["headcount"] for r in adjusted_by_role),
            "by_role": adjusted_by_role,
            "assumptions": {
                **estimate["assumptions"],
                "complexity": complexity,
                "complexity_buffer": buffer,
            },
        }
    }
