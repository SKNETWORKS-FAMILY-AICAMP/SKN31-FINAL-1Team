"""Deterministic quality checks for generated requirement items.

The checks deliberately reuse existing output fields so requirement quality can
be enforced without a database migration. ``related_feature`` carries the plan
field and evidence excerpt, while ``review_status`` and ``note`` continue to
represent unresolved or proposed details.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from .schemas import ItemReviewStatus, PlanDocument, RequirementItem, Source


PLAN_EVIDENCE_FIELDS = (
    "goal",
    "overview",
    "background",
    "target_users",
    "key_features",
    "tech_stack",
    "final_decisions",
    "problem_definition",
    "user_scenarios",
    "requirements",
)

# These terms materially constrain implementation. They are allowed only when
# the plan itself contains them. This list is intentionally conservative and
# should contain architecture choices, not ordinary implementation verbs.
DESIGN_TERMS = (
    "이벤트 소싱",
    "event sourcing",
    "라우팅 캐시",
    "캐시",
    "cache",
    "요청 큐",
    "메시지 큐",
    "queue",
    "익명화",
    "anonymization",
    "실험 플래그",
    "기능 플래그",
    "feature flag",
    "메시지 브로커",
    "kafka",
    "rabbitmq",
    "redis",
    "수동 트리거",
    "수동 재처리",
    "웹훅",
    "webhook",
    "crud",
    "작업 큐",
    "큐 레코드",
    "파이프라인",
    "외부 반영",
    "dns",
    "방화벽",
    "레지스트리",
    "버전 이력",
    "이벤트 스트림",
    "이력 테이블",
    "대시보드",
    "규칙 기반",
    "쿼터",
    "자격 증명 갱신",
    "최소 권한",
    "변경 불가능",
    "운영 옵션",
    "설정 옵션",
    "외부화",
    "트리거",
    "타임스탬프",
    "샌드박스",
)

PLACEHOLDER_TERMS = (
    "후속 확정",
    "추후 확정",
    "별도 협의",
    "향후 결정",
    "미정",
)
SUBJECTIVE_TERMS = (
    "적절한",
    "빠르게",
    "신속하게",
    "안정적으로",
    "충분한",
    "효율적으로",
    "사용하기 쉽게",
)
TEST_METHOD_TERMS = (
    "테스트",
    "검증",
    "확인",
    "측정",
    "로그",
    "조회",
    "비교",
)
OBSERVABLE_TERMS = (
    "반환",
    "저장",
    "생성",
    "표시",
    "차단",
    "거부",
    "성공",
    "실패",
    "일치",
    "누락",
    "중복",
    "오류",
    "변경",
    "전달",
    "처리",
)

_EVIDENCE_PATTERN = re.compile(r"^\[(?P<field>[a-z_]+)\]\s*(?P<excerpt>.+)$")
_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣_.+/-]*")
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:%|ms|초|분|시간|일|건|명|개|회|MB|GB|TPS|RPS)", re.I)
_COMPARATOR_PATTERN = re.compile(r"이하|이상|미만|초과|내(?:에|로)|넘지|최소|최대|같(?:다|은)")


@dataclass(frozen=True)
class RequirementQualityIssue:
    requirement_id: str
    code: str
    message: str

    def as_prompt_line(self) -> str:
        return f"- {self.requirement_id} [{self.code}] {self.message}"


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _plan_field_text(plan: PlanDocument, field: str) -> str:
    if field == "requirements":
        return "\n".join(item.content for item in plan.requirements)
    return str(getattr(plan, field, "") or "")


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(value)
        if len(token) >= 2
    }


def _grounding_issues(plan: PlanDocument, item: RequirementItem) -> list[RequirementQualityIssue]:
    if item.source == Source.BASELINE_DEFAULT:
        if item.review_status != ItemReviewStatus.PENDING:
            return [
                RequirementQualityIssue(
                    item.id,
                    "BASELINE_NOT_PENDING",
                    "baseline_default 항목은 검토대기여야 한다.",
                )
            ]
        return []

    match = _EVIDENCE_PATTERN.match(item.related_feature.strip())
    if not match:
        return [
            RequirementQualityIssue(
                item.id,
                "EVIDENCE_FORMAT",
                "related_feature를 '[기획서필드] 원문 핵심 구절' 형식으로 작성해야 한다.",
            )
        ]

    field = match.group("field")
    excerpt = match.group("excerpt")
    if field not in PLAN_EVIDENCE_FIELDS:
        return [
            RequirementQualityIssue(
                item.id,
                "EVIDENCE_FIELD",
                f"근거 필드 '{field}'는 허용된 기획서 필드가 아니다.",
            )
        ]

    source_text = _plan_field_text(plan, field)
    source_tokens = _tokens(source_text)
    excerpt_tokens = _tokens(excerpt)
    overlap = source_tokens & excerpt_tokens
    minimum_overlap = 1 if len(excerpt_tokens) <= 2 else 2
    if not source_text.strip() or len(overlap) < minimum_overlap:
        return [
            RequirementQualityIssue(
                item.id,
                "EVIDENCE_NOT_FOUND",
                f"related_feature의 근거 구절을 기획서 {field}에서 확인할 수 없다.",
            )
        ]
    return []


def _unsupported_design_issues(
    plan: PlanDocument, item: RequirementItem
) -> list[RequirementQualityIssue]:
    plan_text = _normalize(
        "\n".join(_plan_field_text(plan, field) for field in PLAN_EVIDENCE_FIELDS)
    )
    item_text = _normalize(
        "\n".join(
            (
                item.title,
                item.description,
                item.input_output,
                item.acceptance_criteria,
                item.note,
            )
        )
    )
    issues = []
    invented = [term for term in DESIGN_TERMS if term in item_text and term not in plan_text]
    if invented:
        issues.append(
            RequirementQualityIssue(
                item.id,
                "UNSUPPORTED_DESIGN",
                f"기획서에 없는 구현 기술 또는 설계가 포함됐다: {', '.join(sorted(set(invented)))}.",
            )
        )

    plan_numbers = {value.lower().replace(" ", "") for value in _NUMBER_PATTERN.findall(plan_text)}
    acceptance_numbers = {
        value.lower().replace(" ", "")
        for value in _NUMBER_PATTERN.findall(item.acceptance_criteria)
    }
    ungrounded_acceptance_numbers = sorted(acceptance_numbers - plan_numbers)
    if item.source == Source.REQUIREMENT_TEXT and ungrounded_acceptance_numbers:
        issues.append(
            RequirementQualityIssue(
                item.id,
                "ACCEPTANCE_UNGROUNDED_NUMBER",
                "기획서에 없는 수치가 인수조건에 포함됐다: "
                + ", ".join(ungrounded_acceptance_numbers)
                + ".",
            )
        )
    return issues


def _acceptance_issues(item: RequirementItem) -> list[RequirementQualityIssue]:
    criteria = item.acceptance_criteria.strip()
    normalized = _normalize(criteria)
    if any(term in normalized for term in PLACEHOLDER_TERMS):
        return [
            RequirementQualityIssue(
                item.id,
                "ACCEPTANCE_PLACEHOLDER",
                "acceptance_criteria를 '후속 확정/미정'으로 남기지 말고 검증 가능한 조건으로 작성해야 한다.",
            )
        ]

    has_number = bool(_NUMBER_PATTERN.search(criteria))
    has_comparator = bool(_COMPARATOR_PATTERN.search(criteria))
    has_method = any(term in normalized for term in TEST_METHOD_TERMS)
    has_observable = any(term in normalized for term in OBSERVABLE_TERMS)
    has_behavior_shape = (
        ("given" in normalized and "when" in normalized and "then" in normalized)
        or ("경우" in criteria and ("해야" in criteria or "되는지" in criteria))
    )
    measurable = (has_number and (has_comparator or has_method)) or (
        has_method and has_observable
    ) or has_behavior_shape
    if not measurable:
        return [
            RequirementQualityIssue(
                item.id,
                "ACCEPTANCE_NOT_VERIFIABLE",
                "측정값·임계값 또는 시험 방법과 관찰 가능한 합격 결과가 필요하다.",
            )
        ]
    if any(term in normalized for term in SUBJECTIVE_TERMS) and not has_number:
        return [
            RequirementQualityIssue(
                item.id,
                "ACCEPTANCE_SUBJECTIVE",
                "주관적 표현은 수치 또는 명확한 통과/실패 조건으로 바꿔야 한다.",
            )
        ]
    return []


def validate_requirement_item(
    plan: PlanDocument, item: RequirementItem
) -> list[RequirementQualityIssue]:
    return [
        *_grounding_issues(plan, item),
        *_unsupported_design_issues(plan, item),
        *_acceptance_issues(item),
    ]


def collect_requirement_quality_issues(
    plan: PlanDocument, items: Sequence[RequirementItem] | Iterable[RequirementItem]
) -> list[RequirementQualityIssue]:
    return [issue for item in items for issue in validate_requirement_item(plan, item)]


def format_quality_issues(issues: Sequence[RequirementQualityIssue]) -> str:
    return "\n".join(issue.as_prompt_line() for issue in issues)
