"""원문 기반 1~4번 작성 계약과 결정적 렌더링."""

import json
from html import escape
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from meeting_analysis.validators.evidence import is_quote_verified
from shared.schemas_base import Evidence
from .prompt_loader import load_plan_template
from .schemas import Feature, PlanSection, VerifiedEvidence


class CitedParagraph(BaseModel):
    text: str
    evidence: list[Evidence] = Field(default_factory=list)


class OverviewDraft(BaseModel):
    service_overview: CitedParagraph
    data_scope: CitedParagraph
    current_and_future: CitedParagraph
    review_questions: list[str] = Field(default_factory=list)


class CoreGoalDraft(BaseModel):
    core_goal: CitedParagraph
    approach: CitedParagraph
    review_questions: list[str] = Field(default_factory=list)


class DetailedGoalDraft(BaseModel):
    title: str
    problem: str
    direction: str
    evidence: list[Evidence] = Field(default_factory=list)
    is_proposal: bool = False


class GoalsDraft(BaseModel):
    goals: list[DetailedGoalDraft] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class UserDraft(BaseModel):
    name: str
    description: str
    usage: str
    evidence: list[Evidence] = Field(default_factory=list)
    is_proposal: bool = False


class UsersDraft(BaseModel):
    users: list[UserDraft] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class ContextPlan(BaseModel):
    overview: OverviewDraft
    problem: CoreGoalDraft
    goals: GoalsDraft
    users: UsersDraft
    features: list[Feature] = Field(default_factory=list)


SECTION_MODELS = {
    "overview": OverviewDraft,
    "problem": CoreGoalDraft,
    "goals": GoalsDraft,
    "users": UsersDraft,
}


def system_prompt(glossary_text: str = "") -> str:
    path = Path(__file__).parent / "prompt_templates" / "context_generation.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules["features_rules"] = load_plan_template()["features_rules"]
    rules["glossary_rules"] = load_plan_template()["glossary_rules"]
    return json.dumps(rules, ensure_ascii=False) + "\n용어집(참고 자료):\n" + glossary_text


def _verified_evidence(
    evidence_items: list[Evidence], source: str, evidence: dict[str, VerifiedEvidence]
) -> bool:
    if not evidence_items:
        return False
    all_valid = True
    for item in evidence_items:
        if is_quote_verified(item.quote, source):
            evidence[item.quote] = VerifiedEvidence(quote=item.quote, status="verified")
        else:
            all_valid = False
    return all_valid


def _review_html(notes: list[str]) -> str:
    notes = list(dict.fromkeys(note.strip() for note in notes if note.strip()))
    if not notes:
        return ""
    return "<p><strong>PM 확인 사항</strong></p><ul>" + "".join(
        f"<li>{escape(note)}</li>" for note in notes
    ) + "</ul>"


def _paragraph(
    item: CitedParagraph,
    label: str,
    source: str,
    evidence: dict[str, VerifiedEvidence],
    notes: list[str],
) -> str:
    if not item.text.strip():
        return ""
    if not _verified_evidence(item.evidence, source, evidence):
        notes.append(f"{label}의 작성 근거를 회의록 원문과 대조해 확인해 주세요.")
    return f"<p>{escape(item.text.strip())}</p>"


def render_section(section, source: str, spec: dict) -> PlanSection:
    """섹션별 고정 템플릿으로 렌더링합니다."""
    evidence: dict[str, VerifiedEvidence] = {}
    notes = list(section.review_questions)
    parts: list[str] = []
    items: list[str] = []

    if spec["key"] == "overview":
        parts.extend(filter(None, [
            _paragraph(section.service_overview, "서비스 개요", source, evidence, notes),
            _paragraph(section.data_scope, "데이터 범위", source, evidence, notes),
            _paragraph(section.current_and_future, "현재 상태와 향후 방향", source, evidence, notes),
        ]))
    elif spec["key"] == "problem":
        parts.extend(filter(None, [
            _paragraph(section.core_goal, "핵심 목표", source, evidence, notes),
            _paragraph(section.approach, "주요 추진 방향", source, evidence, notes),
        ]))
    elif spec["key"] == "goals":
        for goal in section.goals:
            if not goal.title.strip() or not goal.problem.strip() or not goal.direction.strip():
                continue
            if not _verified_evidence(goal.evidence, source, evidence):
                notes.append(f"{goal.title}의 작성 근거를 회의록 원문과 대조해 확인해 주세요.")
            if goal.is_proposal:
                notes.append(f"{goal.title}의 추진 목표를 기획서 목표로 사용할지 확인이 필요합니다.")
            parts.extend([
                f"<p><strong>{escape(goal.title.strip())}</strong></p>",
                f"<p><strong>문제:</strong> {escape(goal.problem.strip())}</p>",
                f"<p><strong>추진 목표:</strong> {escape(goal.direction.strip())}</p>",
            ])
            items.append(
                f"{goal.title.strip()}\n문제: {goal.problem.strip()}\n추진 목표: {goal.direction.strip()}"
            )
    elif spec["key"] == "users":
        for user in section.users:
            if not user.name.strip() or not user.description.strip():
                continue
            if not _verified_evidence(user.evidence, source, evidence):
                notes.append(f"{user.name} 사용자 설명의 근거를 회의록 원문과 대조해 확인해 주세요.")
            if user.is_proposal:
                notes.append(f"{user.name}을 서비스 대상 사용자로 정의할지 확인이 필요합니다.")
            parts.append(f"<p><strong>{escape(user.name.strip())}</strong></p>")
            parts.append(f"<p>{escape(user.description.strip())}</p>")
            if user.usage.strip():
                parts.append(f"<p>{escape(user.usage.strip())}</p>")
    else:
        raise ValueError(f"원문 기반 렌더링을 지원하지 않는 섹션입니다: {spec['key']}")

    notes = list(dict.fromkeys(note.strip() for note in notes if note.strip()))
    body_exists = bool(parts)
    parts.append(_review_html(notes))
    return PlanSection(
        no=spec["no"], key=spec["key"], title=spec["title"], section_type=spec["type"],
        content_html="".join(parts), items=items,
        source_fields=["plan_source_text"], evidence=list(evidence.values()),
        needs_input="\n".join(notes), is_incomplete=not body_exists,
    )
