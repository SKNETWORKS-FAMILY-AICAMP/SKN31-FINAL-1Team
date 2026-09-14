# tasks/test_scheduler.py
"""
2026-09-11 (Phase 1): tasks.scheduler 골든 테스트.
결정적 모듈이므로 입력 -> 정확한 날짜를 그대로 못박는다.
"""
from datetime import date

from django.test import SimpleTestCase

from assignee_recommend.rule_filter import list_project_workdays
from tasks.scheduler import (
    DEFAULT_RISK_BUFFER,
    MAX_RISK_BUFFER,
    ScheduleError,
    _sane_buffer,
    plan_days,
    schedule,
)

# 2026-09: 09-01(화) ~ 09-30(수), 평일 22일. 인덱스 예시:
#   0=09-01  1=09-02  2=09-03  3=09-04  4=09-07  5=09-08 ...  21=09-30
WORKDAYS = list_project_workdays(date(2026, 9, 1), date(2026, 9, 30))


def _u(unit_id, assignee_id, hours, depends_on=None, buffer=None):
    return {
        "unit_id": unit_id,
        "assignee_id": assignee_id,
        "estimated_hours": hours,
        "risk_buffer_factor": buffer,
        "depends_on": depends_on or [],
    }


class PlanDaysTests(SimpleTestCase):
    def test_buffer_stretches_short_task(self):
        # 6h: ceil(6 * 1.2 / 6) = 2일  (기존 round(6/8)=1일 대비 여유 확보)
        self.assertEqual(plan_days(6, DEFAULT_RISK_BUFFER), 2)

    def test_minimum_one_day(self):
        self.assertEqual(plan_days(0, DEFAULT_RISK_BUFFER), 1)
        self.assertEqual(plan_days(None, DEFAULT_RISK_BUFFER), 1)

    def test_focus_hours_param(self):
        self.assertEqual(plan_days(24, 1.0, focus_hours_per_day=6), 4)
        self.assertEqual(plan_days(24, 1.0, focus_hours_per_day=8), 3)


class SaneBufferTests(SimpleTestCase):
    """2026-09-11 (Phase 2): LLM이 준 risk_buffer_factor 검산."""

    def test_none_or_sub_one_falls_back_to_default(self):
        self.assertEqual(_sane_buffer(None, DEFAULT_RISK_BUFFER), DEFAULT_RISK_BUFFER)
        self.assertEqual(_sane_buffer(0.5, DEFAULT_RISK_BUFFER), DEFAULT_RISK_BUFFER)

    def test_huge_value_is_capped(self):
        self.assertEqual(_sane_buffer(10.0, DEFAULT_RISK_BUFFER), MAX_RISK_BUFFER)

    def test_reasonable_value_passes_through(self):
        self.assertEqual(_sane_buffer(1.5, DEFAULT_RISK_BUFFER), 1.5)

    def test_unit_buffer_changes_schedule_length(self):
        base = schedule([{"unit_id": "T", "assignee_id": 1, "estimated_hours": 12,
                          "risk_buffer_factor": None, "depends_on": []}], WORKDAYS)
        heavy = schedule([{"unit_id": "T", "assignee_id": 1, "estimated_hours": 12,
                           "risk_buffer_factor": 2.0, "depends_on": []}], WORKDAYS)
        self.assertLess(base["units"]["T"]["end_date"], heavy["units"]["T"]["end_date"])


class ContiguousSchedulingTests(SimpleTestCase):
    def test_single_assignee_tasks_are_back_to_back(self):
        res = schedule([_u("T1", 1, 6), _u("T2", 1, 6), _u("T3", 1, 12)], WORKDAYS)
        u = res["units"]
        self.assertEqual((u["T1"]["start_date"], u["T1"]["end_date"]), ("2026-09-01", "2026-09-02"))
        self.assertEqual((u["T2"]["start_date"], u["T2"]["end_date"]), ("2026-09-03", "2026-09-04"))
        # T3 = 3일: 09-07(월) ~ 09-09  (09-05,06 주말 건너뜀)
        self.assertEqual((u["T3"]["start_date"], u["T3"]["end_date"]), ("2026-09-07", "2026-09-09"))

    def test_assignees_are_independent(self):
        res = schedule([_u("A", 1, 6), _u("B", 2, 6)], WORKDAYS)
        self.assertEqual(res["units"]["A"]["start_date"], "2026-09-01")
        self.assertEqual(res["units"]["B"]["start_date"], "2026-09-01")

    def test_summary_reports_buffer_not_gap(self):
        res = schedule([_u("A", 1, 6)], WORKDAYS)
        s = res["summary"]
        self.assertEqual(s["projected_finish_date"], "2026-09-02")
        self.assertEqual(s["project_buffer_days"], 20)  # 21 - 1
        self.assertFalse(s["exceeds_project_period"])
        self.assertTrue(s["feasible"])


class ScheduleReasonTests(SimpleTestCase):
    """2026-09-11 (Phase 4): 시작일 근거 문장 — 전부 결정적."""

    def test_first_task_reason_is_project_start(self):
        res = schedule([_u("T1", 1, 6)], WORKDAYS)
        self.assertIn("프로젝트 시작일", res["units"]["T1"]["schedule_reason"])

    def test_second_task_reason_is_continuation(self):
        res = schedule([_u("T1", 1, 6), _u("T2", 1, 6)], WORKDAYS)
        self.assertIn("이어서", res["units"]["T2"]["schedule_reason"])

    def test_dependent_reason_names_predecessor(self):
        units = [
            {"unit_id": "A", "title": "ERD 설계", "assignee_id": 1, "estimated_hours": 6,
             "risk_buffer_factor": None, "depends_on": []},
            {"unit_id": "B", "title": "API 구현", "assignee_id": 2, "estimated_hours": 6,
             "risk_buffer_factor": None, "depends_on": ["A"]},
        ]
        res = schedule(units, WORKDAYS)
        self.assertIn("ERD 설계", res["units"]["B"]["schedule_reason"])
        self.assertIn("선행", res["units"]["B"]["schedule_reason"])

    def test_overflow_reason_flags_review(self):
        res = schedule([_u("BIG", 1, 400)], WORKDAYS)
        self.assertIn("검토", res["units"]["BIG"]["schedule_reason"])


class DependencyTests(SimpleTestCase):
    def test_dependent_starts_after_predecessor_across_assignees(self):
        # B는 담당자가 놀고 있어도 A가 끝나야 시작 — 이때 생기는 공백은 정상
        res = schedule([_u("A", 1, 6), _u("B", 2, 6, depends_on=["A"])], WORKDAYS)
        self.assertEqual(res["units"]["A"]["end_date"], "2026-09-02")
        self.assertEqual(res["units"]["B"]["start_date"], "2026-09-03")

    def test_dependency_order_independent_of_input_order(self):
        # 입력은 B, A 순서지만 B가 A에 의존 -> 위상정렬이 A를 먼저 배치
        res = schedule([_u("B", 1, 6, depends_on=["A"]), _u("A", 1, 6)], WORKDAYS)
        self.assertEqual((res["units"]["A"]["start_date"], res["units"]["A"]["end_date"]),
                         ("2026-09-01", "2026-09-02"))
        self.assertEqual(res["units"]["B"]["start_date"], "2026-09-03")

    def test_cycle_raises(self):
        with self.assertRaises(ScheduleError):
            schedule([_u("A", 1, 6, depends_on=["B"]), _u("B", 1, 6, depends_on=["A"])], WORKDAYS)

    def test_dangling_dependency_is_ignored(self):
        res = schedule([_u("A", 1, 6, depends_on=["NOPE"]), _u("B", 1, 6)], WORKDAYS)
        self.assertEqual(res["units"]["A"]["start_date"], "2026-09-01")


class OverflowTests(SimpleTestCase):
    def test_overflow_flagged_and_clamped_not_truncated(self):
        res = schedule([_u("BIG", 1, 400)], WORKDAYS)  # plan_days = 80일
        u = res["units"]["BIG"]
        self.assertTrue(u["exceeds_project_period"])
        self.assertEqual(u["start_date"], "2026-09-01")
        self.assertEqual(u["end_date"], "2026-09-30")  # 마지막 평일로 클램프
        s = res["summary"]
        self.assertTrue(s["exceeds_project_period"])
        self.assertFalse(s["feasible"])
        self.assertLess(s["project_buffer_days"], 0)  # 음수 = 초과 일수

    def test_no_workdays(self):
        res = schedule([_u("A", 1, 6)], [])
        self.assertIsNone(res["units"]["A"]["start_date"])
        self.assertTrue(res["units"]["A"]["exceeds_project_period"])
        self.assertEqual(res["summary"]["projected_finish_date"], None)
        self.assertFalse(res["summary"]["feasible"])


class UnassignedTests(SimpleTestCase):
    def test_unassigned_unit_has_no_dates_and_is_excluded_from_summary(self):
        res = schedule([_u("A", None, 6)], WORKDAYS)
        self.assertIsNone(res["units"]["A"]["start_date"])
        self.assertIsNone(res["units"]["A"]["end_date"])
        self.assertFalse(res["units"]["A"]["exceeds_project_period"])
        self.assertIsNone(res["summary"]["projected_finish_date"])
        self.assertTrue(res["summary"]["feasible"])
