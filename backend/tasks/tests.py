# tasks/tests.py
from datetime import date

from django.test import SimpleTestCase, TestCase

from tasks.services import _build_plan_review, _planned_days, _schedule_suggestion_dates
from tasks.scheduler import DEFAULT_RISK_BUFFER, FOCUS_HOURS_PER_DAY
from tasks.planning_context import build_employee_profiles, build_project_context

# 스케줄러 알고리즘 자체의 골든 테스트는 tasks/test_scheduler.py 에 있다.
# 여기서는 _schedule_suggestion_dates 의 "suggestions <-> scheduler 형태 변환"만 본다.


class PlanningContextTests(TestCase):
    """2026-09-11 (Phase 3 item 9): 컨텍스트 빌더."""

    def test_project_context_has_workdays(self):
        ctx = build_project_context("2026-09-01", "2026-09-30")
        self.assertEqual(ctx["total_workdays"], 22)
        self.assertEqual(ctx["workdays"][0], "2026-09-01")

    def test_employee_profiles_returns_list(self):
        # 빈 DB에서도 안전하게 리스트를 돌려준다(스키마 확인용).
        self.assertIsInstance(build_employee_profiles(), list)


class PlanReviewTests(SimpleTestCase):
    """2026-09-11 (Phase 4): 확정 전 손볼 항목 집계(결정적)."""

    def test_collects_held_and_over_period(self):
        suggestions = [
            {"unit_id": "T1", "title": "정상", "assignee_id": 1, "review_required": False,
             "exceeds_project_period": False},
            {"unit_id": "T2", "title": "보류건", "assignee_id": None, "review_required": True,
             "hold_explanation": "스킬 맞는 후보 없음", "exceeds_project_period": False},
            {"unit_id": "T3", "title": "초과건", "assignee_id": 2, "assignee_name": "김backend",
             "review_required": False, "exceeds_project_period": True},
        ]
        review = _build_plan_review(suggestions)
        self.assertEqual([h["unit_id"] for h in review["held_units"]], ["T2"])
        self.assertEqual([o["unit_id"] for o in review["over_period_units"]], ["T3"])
        self.assertTrue(review["needs_attention"])

    def test_clean_plan_needs_no_attention(self):
        suggestions = [
            {"unit_id": "T1", "title": "a", "assignee_id": 1, "review_required": False,
             "exceeds_project_period": False},
        ]
        self.assertFalse(_build_plan_review(suggestions)["needs_attention"])


class ReExportTests(SimpleTestCase):
    """2026-09-11 (Phase 1): 정책 상수/함수는 tasks.scheduler 로 옮기고
    services 는 재노출만 한다 — 기존 import 경로가 계속 살아있는지 확인."""

    def test_planned_days_reexport(self):
        self.assertEqual(_planned_days(6, DEFAULT_RISK_BUFFER), 2)

    def test_focus_hours_constant_sane(self):
        self.assertLessEqual(FOCUS_HOURS_PER_DAY, 8.0)


class ScheduleSuggestionDatesAdapterTests(SimpleTestCase):
    """2026-09-11 (Phase 1): scheduler 결과가 suggestions 각 항목과 summary 로
    올바르게 옮겨지는지."""

    START = date(2026, 9, 1)   # 화
    END = date(2026, 9, 30)    # 수 (평일 22일)

    def _run(self, suggestions):
        return _schedule_suggestion_dates(suggestions, self.START, self.END)

    def test_writes_dates_back_onto_each_suggestion(self):
        suggestions = [
            {"unit_id": "T1", "assignee_id": 1, "estimated_hours": 6},
            {"unit_id": "T2", "assignee_id": 1, "estimated_hours": 12},
        ]
        summary = self._run(suggestions)
        self.assertEqual(suggestions[0]["suggested_start_date"], "2026-09-01")
        self.assertEqual(suggestions[1]["suggested_start_date"], "2026-09-03")  # 갭 없음
        self.assertFalse(suggestions[0]["exceeds_project_period"])
        self.assertEqual(summary["projected_finish_date"], suggestions[1]["suggested_end_date"])
        self.assertGreater(summary["project_buffer_days"], 0)
        self.assertTrue(summary["feasible"])

    def test_unassigned_suggestion_gets_null_dates(self):
        suggestions = [{"unit_id": "T1", "assignee_id": None, "estimated_hours": 6}]
        summary = self._run(suggestions)
        self.assertIsNone(suggestions[0]["suggested_start_date"])
        self.assertIsNone(suggestions[0]["suggested_end_date"])
        self.assertIsNone(summary["projected_finish_date"])

    def test_overflow_flag_propagates_to_suggestion_and_summary(self):
        suggestions = [{"unit_id": "T1", "assignee_id": 1, "estimated_hours": 400}]
        summary = self._run(suggestions)
        self.assertTrue(suggestions[0]["exceeds_project_period"])
        self.assertIsNotNone(suggestions[0]["suggested_end_date"])  # 클램프, 안 죽음
        self.assertTrue(summary["exceeds_project_period"])
        self.assertLess(summary["project_buffer_days"], 0)

    def test_depends_on_is_forwarded(self):
        suggestions = [
            {"unit_id": "A", "assignee_id": 1, "estimated_hours": 6},
            {"unit_id": "B", "assignee_id": 2, "estimated_hours": 6, "depends_on": ["A"]},
        ]
        self._run(suggestions)
        self.assertEqual(suggestions[0]["suggested_end_date"], "2026-09-02")
        self.assertEqual(suggestions[1]["suggested_start_date"], "2026-09-03")
