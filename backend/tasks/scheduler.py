# tasks/scheduler.py
"""
2026-09-11 (Phase 1): 업무 일정 배치를 결정적으로 계산하는 순수 모듈.

Phase 0에서 services._schedule_suggestion_dates 안에 있던 ASAP 연속 배치 로직을
독립 함수로 빼내고, 업무 간 의존성(선행 관계)까지 다룰 수 있게 확장했다. LLM은
관여하지 않는다 — 담당자·공수·의존성은 입력으로 받고, 이 모듈은 "언제 시작해서
언제 끝나는지"만 계산한다("코드가 결정, LLM은 서술만" 원칙).

의존성/버퍼 계수는 Phase 2에서 task_generation이 채운다. 없으면(Phase 1 현재)
depends_on=[], risk_buffer_factor=기본값으로 동작해 Phase 0과 같은 결과를 낸다.
"""

import logging
from collections import deque
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

# 2026-09-11: 일정 계산 정책 상수·환산 함수의 정본 위치를 ai/assignee_recommend/
# rule_filter.py로 옮겼다 — schedule_assignments()(담당자 배정의 용량 게이트)도
# 똑같은 환산이 필요해졌는데, ai/는 backend에 의존할 수 없어(반대 방향은 되지만)
# 여기서 재노출하는 대신 저쪽이 정본이고 여기가 가져다 쓰는 구조로 바꿨다.
# 두 곳이 각자 정의하면 다시 어긋나기 쉽다(실제로 배정 시점 8h/버퍼없음 vs
# 일정 시점 6h/버퍼있음이 서로 달라 담당자 1명 일정이 초과되는 사고가 있었다).
from assignee_recommend.rule_filter import (
    DEFAULT_RISK_BUFFER,
    FOCUS_HOURS_PER_DAY,
    MAX_RISK_BUFFER,
    _sane_buffer,
    plan_days,
)

logger = logging.getLogger(__name__)


class ScheduleError(ValueError):
    """의존성 순환처럼 일정을 계산할 수 없는 입력."""


def _topo_order(units_by_id: Dict[str, dict]) -> List[str]:
    """
    Kahn 위상정렬. 준비 상태가 같으면 입력(units_by_id 삽입) 순서를 유지한다 —
    units_by_id는 우선순위 정렬된 순서로 들어오므로 그 순서가 보존된다.

    존재하지 않는 unit_id를 가리키는 depends_on 항목은 무시한다(만족된 것으로
    취급) — LLM이 재번호된 ID를 잘못 참조해도 전체 일정이 깨지지 않게.
    순환이 있으면 ScheduleError.
    """
    indegree: Dict[str, int] = {uid: 0 for uid in units_by_id}
    dependents: Dict[str, List[str]] = {uid: [] for uid in units_by_id}
    for uid, u in units_by_id.items():
        seen = set()
        for dep in u.get("depends_on") or []:
            if dep in units_by_id and dep != uid and dep not in seen:
                seen.add(dep)
                indegree[uid] += 1
                dependents[dep].append(uid)

    ready = deque(uid for uid in units_by_id if indegree[uid] == 0)
    order: List[str] = []
    while ready:
        uid = ready.popleft()
        order.append(uid)
        for nxt in dependents[uid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)

    if len(order) != len(units_by_id):
        cyclic = sorted(uid for uid in units_by_id if indegree[uid] > 0)
        raise ScheduleError(f"업무 의존성에 순환이 있습니다: {cyclic}")
    return order


def schedule(
    units: Sequence[dict],
    workdays: Sequence[date],
    *,
    focus_hours_per_day: float = FOCUS_HOURS_PER_DAY,
    default_risk_buffer: float = DEFAULT_RISK_BUFFER,
) -> Dict[str, Any]:
    """
    담당자별로 업무를 프로젝트 평일 위에 ASAP(연속) 배치한다.

    각 unit dict가 갖는 키:
      unit_id            : str
      assignee_id        : Any | None   (None이면 일정 계산 안 함 — 미배정)
      estimated_hours    : float
      risk_buffer_factor : float | None (없으면 default_risk_buffer)
      depends_on         : list[str]    (선행 unit_id, 없으면 [])

    배치 규칙:
      - 같은 담당자의 업무는 앞 업무 종료 다음 평일부터 시작(갭 없음).
      - 선행 업무(depends_on)가 있으면 그 종료 다음 평일 이후로만 시작
        — 이때 생기는 공백은 "의존성 때문"이라 정상이다.
      - 담당자의 누적 소요가 프로젝트 평일 수를 넘으면 잘라내지 않고
        exceeds_project_period=True로만 표시(조회용 날짜만 마지막 평일로 클램프).

    Returns:
      {
        "units": {unit_id: {"start_date": iso|None, "end_date": iso|None,
                            "exceeds_project_period": bool, "schedule_reason": str}},
        "summary": {"projected_finish_date": iso|None, "project_buffer_days": int,
                    "exceeds_project_period": bool, "feasible": bool},
      }
      schedule_reason: 이 unit이 왜 그 날짜에 놓였는지 한 문장(2026-09-11 Phase 4).
        전부 결정적으로 계산된다 — 스케줄러가 시작일을 무엇으로 정했는지 알기 때문.
      project_buffer_days: 계획상 마지막 업무 종료일부터 프로젝트 종료일까지 남는
        평일 수. 일정이 종료일을 넘으면 음수(초과 일수). 남는 기간을 가짜 버퍼로
        흡수하지 않고 그대로 노출한다.
    """
    units_by_id = {u["unit_id"]: u for u in units}
    total_workdays = len(workdays)
    last_idx = total_workdays - 1

    unit_result: Dict[str, dict] = {}
    raw_end_idx: Dict[str, int] = {}      # 클램프 전 실제 종료 인덱스(의존/버퍼 계산용)
    assignee_cursor: Dict[Any, int] = {}  # 담당자별 다음 가용 평일 인덱스
    any_exceeds = False
    latest_display_idx = -1
    latest_raw_idx = -1

    for uid in _topo_order(units_by_id):
        u = units_by_id[uid]
        assignee = u.get("assignee_id")

        if assignee is None:
            unit_result[uid] = {
                "start_date": None, "end_date": None,
                "exceeds_project_period": False, "schedule_reason": "",
            }
            continue

        if total_workdays == 0:
            unit_result[uid] = {
                "start_date": None, "end_date": None,
                "exceeds_project_period": True,
                "schedule_reason": "프로젝트 기간에 평일이 없어 일정을 잡을 수 없음",
            }
            any_exceeds = True
            continue

        buffer = _sane_buffer(u.get("risk_buffer_factor"), default_risk_buffer)
        days = plan_days(u.get("estimated_hours"), buffer, focus_hours_per_day)

        dep_ready_idx = 0
        dep_driver = None  # 시작일을 결정한 선행 unit
        for dep in u.get("depends_on") or []:
            if dep in raw_end_idx and raw_end_idx[dep] + 1 > dep_ready_idx:
                dep_ready_idx = raw_end_idx[dep] + 1
                dep_driver = dep

        cursor = assignee_cursor.get(assignee, 0)
        start_idx = max(cursor, dep_ready_idx)
        end_idx = start_idx + days - 1
        assignee_cursor[assignee] = end_idx + 1
        raw_end_idx[uid] = end_idx

        exceeds = end_idx > last_idx
        any_exceeds = any_exceeds or exceeds
        disp_start = min(start_idx, last_idx)
        disp_end = min(end_idx, last_idx)
        latest_display_idx = max(latest_display_idx, disp_end)
        latest_raw_idx = max(latest_raw_idx, end_idx)

        # 시작일이 무엇에 의해 결정됐는지 (결정적)
        if dep_driver is not None and dep_ready_idx >= cursor:
            dep_title = units_by_id.get(dep_driver, {}).get("title") or dep_driver
            reason = f'선행 작업 "{dep_title}" 완료 후 시작'
        elif start_idx == 0:
            reason = "프로젝트 시작일부터 배치"
        elif start_idx == cursor:
            reason = "담당자의 앞 작업에 이어서 배치"
        else:
            reason = "가용 시점에 배치"
        if exceeds:
            reason += " · 프로젝트 기간을 넘김(검토 필요)"

        unit_result[uid] = {
            "start_date": workdays[disp_start].isoformat(),
            "end_date": workdays[disp_end].isoformat(),
            "exceeds_project_period": exceeds,
            "schedule_reason": reason,
        }

    if latest_display_idx < 0:
        summary = {
            "projected_finish_date": None,
            "project_buffer_days": 0,
            "exceeds_project_period": any_exceeds,
            "feasible": not any_exceeds,
        }
    else:
        summary = {
            "projected_finish_date": workdays[latest_display_idx].isoformat(),
            "project_buffer_days": last_idx - latest_raw_idx,
            "exceeds_project_period": any_exceeds,
            "feasible": not any_exceeds,
        }
    return {"units": unit_result, "summary": summary}
