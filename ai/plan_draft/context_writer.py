"""원문 기반 1~4번 작성 계약과 결정적 렌더링."""

import json
import re
from html import escape
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from meeting_analysis.validators.evidence import is_quote_verified
from shared.schemas_base import Evidence
from .prompt_loader import load_plan_template
from .schemas import Feature, PlanSection, VerifiedEvidence


# 2026-09-18: overview·problem 문단에 저장 구조·수집 주기·모델명 같은 구현
# 세부사항이 새어 들어오는 문제가 실측(무신사 회의록 웹 테스트)으로 확인됐다.
# context_generation.yaml의 프롬프트 지시만으로는 매번 지켜지지 않아서,
# instructor의 reask 메커니즘(validator가 ValueError를 던지면 그 메시지를
# LLM에 그대로 돌려주고 다시 쓰게 함 — meeting_analysis.eligibility의
# model_validator와 같은 원리)으로 강제한다. 패턴은 "GPU"처럼 흔한 단어보다
# 런팟·A100·클래스 개수처럼 이 문맥에서 오탐 가능성이 낮은 신호 위주로 고른다.
IMPLEMENTATION_DETAIL_PATTERN = re.compile(
    r"RDS|오브젝트 스토리지|DB에 적재|런팟|RunPod|A100|Whisper|CLIP|주클로|"
    r"\d+시간마다|\d+개\s*클래스|\d+개\s*채널|\d+,?\d*개\s*(?:어휘|사전)"
)


# 2026-09-18: "{user.name}을 서비스 대상 사용자로 정의할지..."처럼 받침 여부와
# 무관하게 "을"을 고정으로 붙여서, 사용자 이름이 모음으로 끝나면("보호자",
# "이용자" 등) "보호자을"처럼 조사가 틀리는 문제가 실측(다양한 회의록 테스트)
# 으로 3번 재현됐다. 유니코드 한글 완성형 코드포인트 공식(코드 - 0xAC00을
# 28로 나눈 나머지가 0이면 받침 없음)으로 마지막 글자를 판정한다.
_HANGUL_BASE = 0xAC00
_HANGUL_LAST = 0xD7A3


def _has_batchim(word: str) -> bool:
    """word의 마지막 글자(닫는 괄호·따옴표는 건너뜀) 받침 유무를 판정합니다.

    한글이 아닌 문자로 끝나면(영문 이름 등) 판정할 수 없으므로 받침 없음으로
    간주해 "를" 계열을 씁니다 — 한국어 문장에서 더 무난하게 읽힙니다.
    """
    for ch in reversed(word.strip()):
        if ch in ")]}\"'」』〉》":
            continue
        if _HANGUL_BASE <= ord(ch) <= _HANGUL_LAST:
            return (ord(ch) - _HANGUL_BASE) % 28 != 0
        return False
    return False


def _josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """word 뒤에 붙일 조사를 받침 유무에 따라 고릅니다(예: 을/를, 이/가, 은/는)."""
    return with_batchim if _has_batchim(word) else without_batchim


class CitedParagraph(BaseModel):
    text: str
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def no_implementation_detail(cls, value: str) -> str:
        match = IMPLEMENTATION_DETAIL_PATTERN.search(value)
        if match:
            raise ValueError(
                f"이 문단에 저장 구조·수집 주기·모델명 같은 구현 세부사항"
                f"('{match.group()}')이 포함되어 있습니다. 목적과 범위만 남기고, "
                "그 내용은 features(5번)·tech_scope(6번)에서 다루도록 빼고 다시 쓰세요."
            )
        return value


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
                josa = _josa(user.name, "을", "를")
                notes.append(f"{user.name}{josa} 서비스 대상 사용자로 정의할지 확인이 필요합니다.")
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
