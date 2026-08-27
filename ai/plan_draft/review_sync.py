"""
plan_draft/review_sync.py

graph.py의 plan_review_gate가 받은 승인/반려 결정을 backend의 Plan 모델(Django ORM)에
실제로 반영한다.

State 쪽 review_status(검토대기/검토완료 2단계 Enum)와 DB 쪽
approved_by(nullable FK) + approved_at(nullable DATETIME) + reject_reason(nullable VARCHAR)
3컬럼 조합은 표현 방식이 다르므로, 이 모듈이 그 변환을 전담한다.

매핑 규칙:
  승인 -> approved_by = 승인자 UUID, approved_at = 현재시각, reject_reason = NULL
  반려 -> approved_by = NULL,        approved_at = NULL,      reject_reason = 반려 사유 텍스트

사용 전 shared.django_bootstrap이 먼저 import되어 있어야 한다 (graph.py에서 처리).
"""

from datetime import datetime, timezone

from plans.models import Plan  # backend/plans/models.py — django_bootstrap 이후에만 import 가능


def apply_plan_review_decision(
    plan_id: str,                      # 기획.id (UUID) — plan_id == DB의 PK
    decision: str,                      # "승인" | "반려"
    reviewer_id: str | None = None,     # 승인자 UUID. 승인 시 필수
    reject_reason: str | None = None,   # 반려 사유. 반려 시 필수
) -> Plan:
    try:
        plan = Plan.objects.get(id=plan_id)
    except Plan.DoesNotExist as exc:
        raise ValueError(f"기획서를 찾을 수 없습니다: plan_id={plan_id}") from exc

    if decision == "승인":
        if not reviewer_id:
            raise ValueError("승인 처리에는 reviewer_id가 필요합니다")
        plan.approved_by_id = reviewer_id
        plan.approved_at = datetime.now(timezone.utc)
        plan.reject_reason = None
    elif decision == "반려":
        if not reject_reason:
            raise ValueError("반려 처리에는 reject_reason이 필요합니다")
        plan.approved_by = None
        plan.approved_at = None
        plan.reject_reason = reject_reason
    else:
        raise ValueError(f"알 수 없는 decision 값: {decision!r} (승인 또는 반려만 허용)")

    plan.save(update_fields=["approved_by", "approved_at", "reject_reason", "updated_at"])
    return plan
