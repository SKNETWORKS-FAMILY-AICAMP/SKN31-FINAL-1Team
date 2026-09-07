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
from datetime import date
from typing import Any, Dict, List, Union

from assignee_recommend.rule_filter import calculate_max_hours_per_assignee, flatten_assignable_units

# 스킬 문자열 -> 회사 실제 JOB_ROLE 코드. 필요한 스킬이 늘어날 때마다 팀이 채워나가는
# 표이지, 여기 없는 스킬을 없는 셈 치겠다는 뜻이 아니다 — 매핑 안 되면 UNMAPPED_ROLE로
# 눈에 보이게 남긴다(조용히 버리지 않음).
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


def _roles_for_unit(unit: Dict[str, Any]) -> List[str]:
    """유닛의 required_skills 각각을 역할로 변환한다. 매핑표에 없는 스킬,
    또는 required_skills 자체가 비어있으면 UNMAPPED_ROLE 하나로 묶는다."""
    skills = unit.get("required_skills") or []
    if not skills:
        return [UNMAPPED_ROLE]
    return [SKILL_ROLE_MAP.get(s, UNMAPPED_ROLE) for s in skills]


def estimate_team_size(
    tasks: List[Dict[str, Any]],
    project_start_date: Union[str, date],
    project_end_date: Union[str, date],
) -> Dict[str, Any]:
    """
    업무 목록과 프로젝트 기간만으로 역할별/전체 필요인원을 추정한다.

    Args:
        tasks: task_generation_node 출력의 state["tasks"] 그대로
            (Task/Subtask 배열). flatten_assignable_units()로 내부에서
            배정 가능한 최소 단위만 뽑아 쓴다.
        project_start_date / project_end_date: "YYYY-MM-DD" 문자열 또는
            date 객체. calculate_max_hours_per_assignee()에 그대로 넘긴다.

    Returns:
        {"team_size_estimate": {"total_headcount", "by_role", "assumptions"}}
        by_role은 [{"role", "estimated_hours", "headcount"}, ...],
        estimated_hours 내림차순 정렬.
    """
    max_hours = calculate_max_hours_per_assignee(project_start_date, project_end_date)
    units = flatten_assignable_units(tasks)

    hours_by_role: Dict[str, float] = {}
    for unit in units:
        roles = _roles_for_unit(unit)
        share = unit["estimated_hours"] / len(roles)
        for role in roles:
            hours_by_role[role] = hours_by_role.get(role, 0.0) + share

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
