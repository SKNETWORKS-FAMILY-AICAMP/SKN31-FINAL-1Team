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

import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Union

_PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2, None: 3}

# LLM이 자유 텍스트로 쓰는 required_skills(예: "REST API 설계")와 DB 스킬 코드
# (예: "REST API")를 완전 일치로만 비교하면 표기가 조금만 달라도 매칭이 전부
# 실패해 불필요하게 보류(review_required) 처리된다. 흔히 붙는 한글 접미어를
# 제거해 정규화한 뒤 비교하면 이런 표기 차이를 흡수할 수 있다.
_SKILL_MODIFIER_SUFFIXES = ("설계", "개발", "구현", "능력", "역량", "작업", "처리")


def _normalize_skill(skill: str) -> str:
    """대소문자/공백을 정리하고, 끝에 붙은 흔한 한글 접미어를 하나 제거한다."""
    s = re.sub(r"\s+", " ", skill.strip().lower())
    for suffix in _SKILL_MODIFIER_SUFFIXES:
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[: -len(suffix)].strip()
            break
    return s


def _match_skills(
    required: set, member_skills: set, member_levels: Optional[Dict[str, int]] = None
) -> Dict[str, int]:
    """
    required(LLM 자유 텍스트)와 member_skills(DB 스킬 코드) 사이를 정규화 후
    완전 일치 또는 부분 문자열 포함(양방향)까지 확인해 매칭한다. 예를 들어
    "REST API 설계" ↔ "REST API"는 접미어 제거 후 일치, "Django REST"는
    "REST API"와 부분 포함으로 매칭된다.

    반환값: {매칭된 required의 원본 표기: 그 스킬에 대응하는 member 숙련도(1~5)}.
    required 원본 표기를 그대로 키로 두는 이유는 근거 문장(skill_match)에 LLM이
    쓴 표현을 그대로 노출하기 위해서다. 여러 member 스킬이 한 required에 매칭되면
    가장 높은 숙련도를 취한다. member_levels가 없거나 특정 스킬 레벨이 없으면
    3(중간)으로 본다 — 2026-09-11 (Phase 3).

    한계: "pytest"처럼 member_skills(DB 스킬 코드 목록) 자체에 대응 값이 아예
    없는 어휘는 정규화로도 못 잡는다 — DB 스킬 코드 추가나 프롬프트 단의 허용
    어휘 목록 주입이 필요한 별개 사안이다.
    """
    member_levels = member_levels or {}
    # norm -> 그 스킬의 숙련도(같은 norm에 여러 원본이면 최댓값)
    normalized_member: Dict[str, int] = {}
    for s in member_skills:
        norm = _normalize_skill(s)
        lvl = member_levels.get(s, 3)
        normalized_member[norm] = max(normalized_member.get(norm, 0), lvl)

    matched: Dict[str, int] = {}
    for req in required:
        norm_req = _normalize_skill(req)
        if not norm_req:
            continue
        best_level = 0
        for norm_mem, lvl in normalized_member.items():
            if not norm_mem:
                continue
            if norm_req == norm_mem or norm_req in norm_mem or norm_mem in norm_req:
                best_level = max(best_level, lvl)
        if best_level > 0:
            matched[req] = best_level
    return matched

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


def list_project_workdays(
    project_start_date: Union[str, date], project_end_date: Union[str, date]
) -> List[date]:
    """
    calculate_max_hours_per_assignee()와 같은 평일(월~금) 판정 기준으로,
    개수가 아니라 프로젝트 기간 안의 실제 평일 날짜 목록을 반환한다.
    backend/tasks/services.py의 _schedule_suggestion_dates()가 업무별 시작/
    종료일을 계산할 때 이 목록을 그대로 쓴다 — "평일이 뭔지"의 기준을 두
    군데서 따로 정의해 어긋나는 일이 없도록, 이 판정 로직은 여기 한 곳에만 둔다.
    """
    start = _to_date(project_start_date)
    end = _to_date(project_end_date)
    workdays = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            workdays.append(current)
        current += timedelta(days=1)
    return workdays


# ---------------------------------------------------------------------------
# 2026-09-11: 담당자 배정(용량 게이트, 이 파일)과 일정 배치(날짜 계산,
# backend/tasks/scheduler.py)가 "하루에 얼마나 하는지"를 서로 다른 기준으로
# 계산해서 실제로 불일치가 났다 — 배정 시점엔 하루 8시간·버퍼 없음으로 통과시켰는데,
# 일정 시점엔 하루 6시간 집중시간·리스크 버퍼(최대 3배)로 날짜를 놓다 보니
# 같은 시간(hours)이 훨씬 많은 평일을 잡아먹어, 배정은 통과했는데 일정만 프로젝트
# 기간을 넘기는 사고가 있었다(담당자 1명에게 업무 8개가 몰려 일정 5일 초과).
#
# 그래서 "하루에 얼마나 하는지" 환산 함수를 여기(ai/, DB 의존 없음)로 옮기고,
# backend/tasks/scheduler.py는 이 값을 그대로 가져다 쓴다(재노출) — 두 곳이
# 각자 정의하면 다시 어긋나기 쉬우므로 정의는 한 곳에만 둔다.
# ---------------------------------------------------------------------------
FOCUS_HOURS_PER_DAY = 6.0   # 담당자가 하루에 실제 업무에 쓰는 시간(회의·리뷰 제외)
DEFAULT_RISK_BUFFER = 1.2   # 업무별 risk_buffer_factor가 없을 때 기본 버퍼(20%)
MAX_RISK_BUFFER = 3.0       # LLM이 준 값의 상한 — 환각으로 10배 같은 값이 와도 일정이 안 터지게


def _sane_buffer(factor: Optional[float], default: float = DEFAULT_RISK_BUFFER) -> float:
    """LLM이 준 risk_buffer_factor를 검산한다. None이거나 1.0 미만(버퍼는 공수를
    줄이는 게 아님)이면 기본값, 너무 크면 상한."""
    if factor is None or factor < 1.0:
        return default
    return min(factor, MAX_RISK_BUFFER)


def plan_days(
    estimated_hours: Optional[float],
    risk_buffer: float,
    focus_hours_per_day: float = FOCUS_HOURS_PER_DAY,
) -> int:
    """공수(시간) -> 소요 평일 수. 리스크 버퍼를 곱한 뒤 하루 집중시간으로
    나눠 올림한다. 최소 1일. schedule_assignments()의 용량 게이트와
    backend/tasks/scheduler.py의 날짜 배치가 동일하게 쓴다."""
    hours = (estimated_hours or 0) * risk_buffer
    return max(1, math.ceil(hours / focus_hours_per_day))


def flatten_assignable_units(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Task/Subtask 목록에서 실제로 배정 가능한 최소 단위만 뽑아낸다.

    2026-09-11 (Phase 2): Task 단위로 표현된 의존성(dependency_task_ids)을 unit
    단위(depends_on)로 편다 — Task B가 Task A에 의존하면 B에서 나온 모든 unit은
    A에서 나온 모든 unit이 끝나야 시작할 수 있다. risk_buffer_factor / feature_area
    는 Task 값을 그대로 상속한다(Subtask는 별도로 갖지 않음).
    """
    units_by_task: Dict[str, List[str]] = {}
    for task in tasks:
        subs = task.get("subtasks") or []
        units_by_task[task["task_id"]] = (
            [s["subtask_id"] for s in subs] if subs else [task["task_id"]]
        )

    units = []
    for task in tasks:
        dep_unit_ids = [
            uid
            for dep_task_id in task.get("dependency_task_ids") or []
            for uid in units_by_task.get(dep_task_id, [])
        ]
        buffer = task.get("risk_buffer_factor")
        feature = task.get("feature_area")
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
                    "depends_on": dep_unit_ids,
                    "risk_buffer_factor": buffer,
                    "feature_area": feature,
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
                        "depends_on": dep_unit_ids,
                        "risk_buffer_factor": buffer,
                        "feature_area": feature,
                    }
                )
    return units


def sort_units_by_priority(
    units: List[Dict[str, Any]], priority_by_req_id: Dict[str, Optional[str]]
) -> List[Dict[str, Any]]:
    """
    우선순위(요구사항 priority 상속) 순으로 정렬한다. 같은 우선순위 안에서는
    요구사항(source_req_id) 총 estimated_hours 내림차순 — 규모가 큰 요구사항을
    먼저 배정해, 이후 작은 요구사항이 자투리 가용시간에도 들어갈 여지를 남기는
    그리디 휴리스틱이다. priority가 없는(검토대기) 요구사항에서 파생된 업무는
    맨 뒤로 보낸다.

    2026-09-09 수정: 예전엔 "업무 개별" estimated_hours로 정렬해서, 같은
    요구사항 안에서도 시간이 큰 업무가 작은 업무보다 먼저 오는 경우가 있었다
    (예: "반응형 UI 구현"(7h)이 "반응형 UI 설계"(6h)보다 먼저 배정 순서에 놓여,
    설계보다 구현이 먼저 배정되는 모순이 생김). task_generation은 few-shot대로
    한 요구사항 안에서 설계→개발→테스트 순으로 업무를 만드는데, 개별 시간
    기준 정렬이 이 순서를 깨트린 것. 이제는 "묶음 총합"으로만 큰 것부터
    앞에 두고, 같은 묶음 안에서는 안정 정렬(sorted()는 stable)로 원래
    생성 순서(=설계→개발→테스트)를 그대로 보존한다.

    2026-09-11 (Phase 2 item 7): 클러스터 단위가 "요구사항"에서 "WorkPackage"로
    바뀌었다. unit에 package_id가 있으면 그걸로, 없으면 예전처럼 source_req_id로
    묶는다(=동작 동일). 같은 package의 unit을 인접시켜, schedule_assignments와
    일정 스케줄러가 자연히 "한 기능을 한 사람이 이어서" 처리하게 만든다.
    package 우선순위는 묶음 내 unit 중 가장 높은 요구사항 priority를 쓴다.
    """
    def cluster_of(u: Dict[str, Any]) -> str:
        return u.get("package_id") or f"req:{u['source_req_id']}"

    cluster_total_hours: Dict[str, float] = {}
    cluster_rank: Dict[str, int] = {}
    for u in units:
        c = cluster_of(u)
        cluster_total_hours[c] = cluster_total_hours.get(c, 0.0) + u["estimated_hours"]
        rank = _PRIORITY_RANK.get(priority_by_req_id.get(u["source_req_id"]), 3)
        cluster_rank[c] = min(cluster_rank.get(c, 3), rank)

    def key(u: Dict[str, Any]):
        c = cluster_of(u)
        return (cluster_rank[c], -cluster_total_hours[c], c)

    return sorted(units, key=key)


def _cohesion_key(unit: Dict[str, Any]) -> str:
    """업무 응집도 판정 기준. package_id가 있으면 그걸로, 없으면 요구사항으로
    대체한다(= Phase 2 이전 동작과 동일). 2026-09-11 (Phase 2 item 7)."""
    return unit.get("package_id") or unit["source_req_id"]


def _fit_score(
    unit: Dict[str, Any],
    member: Dict[str, Any],
    matched_skills: set,
    remaining_ratio: float,
    already_on_same_package: bool,
    qualitative_fit: Optional[float] = None,
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

    already_on_same_package: 이 담당자가 같은 배치 안에서 이미 같은
    WorkPackage(feature_area 기반, 없으면 source_req_id)의 다른 업무를 맡았으면
    True. 예를 들어 게시판 CRUD처럼 한 기능 아래 업무가 여러 개일 때, 스킬
    매칭이 크게 갈리지 않으면 이미 그 기능을 맡고 있는 사람에게 몰아줘서
    컨텍스트 스위칭(여러 사람이 같은 기능을 나눠 맡느라 생기는 소통 비용)을
    줄인다. 가중치(0.20)를 스킬(0.40)보다는 낮게 둬서, 스킬이 아예 안 맞는
    사람에게 억지로 몰아주지는 않는다 — 스킬이 비슷한 후보끼리 갈릴 때 이
    가점이 결정적인 역할을 하도록 설계.
    2026-09-11 (Phase 2 item 7): 기준을 요구사항 -> WorkPackage로 넓혔다.
    feature_area가 없으면 package == 요구사항이라 기존 동작과 같다.

    qualitative_fit: 2026-09-11 (Phase 3 확장) — assignment_ranking.score_candidate_fit()
    이 이 후보의 경력기술서 원문·자격증·스킬 숙련도를 "이 업무 설명과 직접 대조해서"
    판단한 질적 적합도(0~1). 기존엔 유사 경험/자격증을 그냥 개수만 셌는데("결제
    연동 3건"이든 "메뉴판 UI 3건"이든 이 업무가 결제 연동이어도 똑같이 3건 취급),
    이제는 내용이 실제로 맞는지를 본다. None이면(해당 unit을 LLM에 안 물어봤거나
    호출 실패) 기존 개수 기반 계산으로 폴백한다 — 폴백 비율(0.6/0.4)은 원래
    가중치(0.15 유사경험 / 0.10 자격증)와 대수적으로 동일하다.
    """
    required = set(unit.get("required_skills", []))
    if not required:
        skill_ratio = 1.0
    elif member.get("skill_levels"):
        # 2026-09-11 (Phase 3): 매칭된 스킬을 숙련도(1~5 -> 0~1)로 가중한다.
        # 매칭 못 한 required는 0점. Django 5레벨 보유자가 2레벨 보유자보다
        # 같은 Django 업무에서 높은 점수를 받는다.
        skill_ratio = sum(min(lvl, 5) / 5 for lvl in matched_skills.values()) / len(required)
    else:
        # 숙련도 정보가 없는 경로: 예전처럼 "보유 여부"만 본다.
        skill_ratio = len(matched_skills) / len(required)

    if qualitative_fit is not None:
        experience_cert_score = qualitative_fit
    else:
        similar_count = len(member.get("past_similar_tasks", []))
        cert_count = len(member.get("certifications", []))
        experience_cert_score = 0.6 * min(similar_count / 3, 1) + 0.4 * min(cert_count / 2, 1)

    return round(
        0.40 * skill_ratio
        + 0.25 * experience_cert_score  # 경력·자격증 — LLM 질적판단 있으면 그걸, 없으면 개수 기반 폴백
        + 0.15 * remaining_ratio  # 여유 많을수록 가점 — 특정 인원 쏠림 방지
        + 0.20 * (1.0 if already_on_same_package else 0.0),  # 같은 기능(WorkPackage) 담당자 가점 — 업무 응집도
        3,
    )


def schedule_assignments(
    units: List[Dict[str, Any]],
    members: List[Dict[str, Any]],
    current_workload: Dict[str, float],
    max_hours_per_assignee: float,
    total_workdays: int,
    fit_scores: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
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
                 기간에 맞춰 계산한 값. 이제 용량 게이트에는 안 쓰고(아래 참고)
                 근거 문장 표시용으로만 남긴다.
        total_workdays: 프로젝트 기간의 평일 수(len(list_project_workdays(...))).
                 용량 게이트가 실제로 쓰는 상한이다.

                 2026-09-11: 용량 게이트를 "시간"이 아니라 "평일 수"로 본다.
                 예전엔 하루 8시간·버퍼 없음으로 계산한 max_hours_per_assignee로
                 배정 시점의 용량을 확인했는데, backend/tasks/scheduler.py가
                 실제 날짜를 놓을 땐 하루 6시간 집중시간·리스크 버퍼(최대 3배)를
                 썼다 — 그래서 배정 시점엔 통과했는데 일정에서는 기간을 넘기는
                 불일치가 실제로 있었다(담당자 1명에게 업무 8개가 몰려 일정만
                 5일 초과). 이제 두 곳이 plan_days()로 동일하게 "평일 수"를
                 계산해 이 불일치를 없앤다.
        fit_scores: {unit_id: {employee_id: {"score": float, "reason": str}}} —
                 assignment_ranking.score_candidate_fit()의 출력(2026-09-11). 이미
                 스킬로 좁혀진 소수 후보의 경력·자격증·숙련도 "내용"을 이 업무
                 설명과 대조해 LLM이 매긴 질적 적합도. 용량·부하 추적·최종 선택은
                 이 함수(코드)가 그대로 하고, LLM은 이 점수·근거만 준다. 없으면
                 (unit이 스코어링 대상에서 빠졌거나 LLM 호출 전체가 실패) 전부
                 None으로 처리되어 _fit_score가 기존 개수 기반 계산으로 폴백한다.

    Returns:
        unit마다 배정 결과 dict. employee_id가 None이면 보류(review_required).
    """
    workload = dict(current_workload)  # 시간 — 근거 문장 표시용으로만 유지
    # 2026-09-11: 실제 게이트는 평일 수로 본다. 이미 확정된 기존 업무(시간만
    # 있고 버퍼 정보가 없음)는 기본 버퍼로 환산해 "이미 며칠 찼는지" 추정한다.
    workload_days: Dict[str, int] = {
        emp_id: plan_days(hours, DEFAULT_RISK_BUFFER) for emp_id, hours in current_workload.items()
    }
    member_by_id = {m["employee_id"]: m for m in members}
    # 담당자별로 이 배치 안에서 이미 맡은 WorkPackage(_cohesion_key) 집합 — 업무
    # 응집도 가점(_fit_score의 already_on_same_package) 판정에 쓴다.
    assigned_pkgs_by_member: Dict[str, set] = {}

    results = []
    for unit in units:
        required = set(unit.get("required_skills", []))
        unit_fit = (fit_scores or {}).get(unit["unit_id"], {})
        unit_buffer = _sane_buffer(unit.get("risk_buffer_factor"))
        unit_days = plan_days(unit.get("estimated_hours"), unit_buffer)
        best_id: Optional[str] = None
        best_matched: set = set()
        best_score = -1.0

        for m in members:
            emp_id = m["employee_id"]
            projected_days = workload_days.get(emp_id, 0) + unit_days
            if projected_days > total_workdays:
                continue  # 이 업무까지 더하면 프로젝트 기간을 넘기는 사람은 후보에서 제외
            matched = _match_skills(required, set(m.get("skills", [])), m.get("skill_levels"))
            if required and not matched:
                continue  # 요구 기술과 하나도 안 겹치면 제외
            remaining_ratio = (
                1 - (projected_days / total_workdays) if total_workdays > 0 else 0.0
            )
            already_on_same_pkg = _cohesion_key(unit) in assigned_pkgs_by_member.get(emp_id, set())
            qual = unit_fit.get(emp_id, {}).get("score")
            score = _fit_score(unit, m, matched, remaining_ratio, already_on_same_pkg, qualitative_fit=qual)
            if score > best_score:
                best_score, best_id, best_matched = score, emp_id, matched

        if best_id is None:
            results.append({"unit": unit, "employee_id": None})
            continue

        workload[best_id] = workload.get(best_id, 0.0) + (unit.get("estimated_hours") or 0)
        workload_days[best_id] = workload_days.get(best_id, 0) + unit_days
        assigned_pkgs_by_member.setdefault(best_id, set()).add(_cohesion_key(unit))
        m = member_by_id[best_id]
        certifications = m.get("certifications", [])
        similar_n = len(m.get("past_similar_tasks", []))
        # 2026-09-11 (Phase 3): 숙련도 정보가 있으면 근거 문장에 레벨을 함께 노출.
        if best_matched and m.get("skill_levels"):
            skill_list = "/".join(f"{s}(Lv{lvl})" for s, lvl in sorted(best_matched.items()))
        elif best_matched:
            skill_list = "/".join(sorted(best_matched))
        else:
            skill_list = ""
        skill_text = (
            f"{skill_list} 보유, 관련 업무 {similar_n}건 수행"
            if skill_list
            else f"관련 업무 {similar_n}건 수행"
        )
        if certifications:
            skill_text += f", 관련 자격증 {'/'.join(certifications)} 보유"
        # 2026-09-11: LLM이 이 업무 내용과 대조해서 판단한 질적 근거가 있으면 그걸
        # 쓴다("결제 연동 프로젝트 3건 수행, 이 업무와 동일한 PG 연동 경험" 같은
        # 구체적 문장) — 없으면 예전처럼 개수만 세는 문장으로 폴백.
        qual_reason = unit_fit.get(best_id, {}).get("reason")
        similar_experience = qual_reason or f"유사 업무 완료 이력 {len(m.get('past_similar_tasks', []))}건"
        results.append(
            {
                "unit": unit,
                "employee_id": best_id,
                "score": best_score,
                "skill_match": skill_text,
                # 2026-09-11: 시간과 함께 평일 환산치도 보여준다 — 실제 게이트는
                # 평일 기준이라, 시간만 보면 "왜 이 사람이 제외됐는지" PM이 이해하기 어렵다.
                "workload": (
                    f"이번 배정 포함 현재 부하 {workload[best_id]:.1f}시간 · "
                    f"약 {workload_days[best_id]}평일 (프로젝트 {total_workdays}평일, 참고 상한 {max_hours_per_assignee:.1f}시간)"
                ),
                "similar_experience": similar_experience,
            }
        )

    return results
