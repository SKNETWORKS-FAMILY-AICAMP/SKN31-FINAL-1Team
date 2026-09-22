"""기획서 품질을 LLM 호출 없이 검사하고 골든 기준으로 회귀 평가합니다.

운영 생성 경로와 평가 기준을 분리한다. 이 모듈은 네트워크를 사용하지 않으며
PlanDocument를 변경하지도 않는다. 따라서 테스트에서 먼저 오탐을 줄인 뒤 같은
검사기를 운영 경로의 선택적 재작성 조건으로 재사용할 수 있다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Literal

from meeting_analysis.validators.evidence import is_quote_verified
from .generator import PlanningFactIndex
from .schemas import PlanDocument, PlanSection


Severity = Literal["blocking", "warning"]


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    severity: Severity
    section_key: str = ""


@dataclass
class QualityReport:
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def blocking_issues(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.severity == "blocking"]

    @property
    def passed(self) -> bool:
        return not self.blocking_issues


def _plain_text(section: PlanSection) -> str:
    text = re.sub(r"<[^>]+>", " ", section.content_html or "")
    return " ".join(unescape(text).split())


def _normalize(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", (text or "").lower())


def _section_texts(plan: PlanDocument) -> dict[str, str]:
    return {section.key: _plain_text(section) for section in plan.sections}


def _fact_quotes(fact) -> set[str]:
    return {_normalize(item.quote) for item in fact.evidence if item.quote.strip()}


def inspect_plan(
    plan: PlanDocument,
    source: str,
    fact_index: PlanningFactIndex | None = None,
) -> QualityReport:
    """형식, 근거, 논의 상태 충돌을 결정론적으로 검사합니다."""
    issues: list[QualityIssue] = []
    sections = {section.key: section for section in plan.sections}
    required_keys = [
        "overview", "problem", "goals", "users", "features", "tech_scope", "decisions",
    ]
    missing = [key for key in required_keys if key not in sections]
    if missing:
        issues.append(QualityIssue(
            "missing_sections", f"필수 섹션 누락: {', '.join(missing)}", "blocking",
        ))

    seen_keys: set[str] = set()
    for section in plan.sections:
        if section.key in seen_keys:
            issues.append(QualityIssue(
                "duplicate_section", f"중복 섹션: {section.key}", "blocking", section.key,
            ))
        seen_keys.add(section.key)
        if section.is_incomplete:
            issues.append(QualityIssue(
                "incomplete_section", f"내용이 비어 있는 섹션: {section.title}",
                "warning", section.key,
            ))
        for evidence in section.evidence:
            if not is_quote_verified(evidence.quote, source):
                issues.append(QualityIssue(
                    "unverified_evidence",
                    f"원문에서 확인되지 않는 근거: {evidence.quote[:60]}",
                    "blocking", section.key,
                ))

    if not fact_index:
        return QualityReport(issues)

    decision_section = sections.get("decisions")
    feature_section = sections.get("features")
    def related(fact_topic: str, fact_text: str, other: str) -> bool:
        # 사실의 topic과 겹치지 않고 content 안의 일반 명사만 우연히 겹치는 경우
        # (예: 서로 다른 주제가 같은 기능명을 스치듯 언급) 오탐으로 이어지므로,
        # 최소 하나의 겹치는 토큰은 topic에도 존재해야 "관련 있음"으로 인정한다.
        topic_tokens = set(re.findall(r"[0-9a-z가-힣]+", fact_topic.lower()))
        fact_tokens = set(re.findall(r"[0-9a-z가-힣]+", fact_text.lower()))
        other_tokens = set(re.findall(r"[0-9a-z가-힣]+", other.lower()))
        meaningful = {
            token for token in fact_tokens & other_tokens
            if len(token) >= 2 and token not in {"기능", "관련", "결정", "사용", "적용"}
        }
        if not (meaningful & topic_tokens):
            return False
        return len(meaningful) >= 2 or any(len(token) >= 4 for token in meaningful)

    for fact in fact_index.facts:
        quotes = _fact_quotes(fact)
        if not quotes:
            continue
        # proposed/unresolved는 시간상 "이후에" 나온 확정만 그 사실을 대체할 수 있지만,
        # rejected는 그 자체로 이미 해당 주제가 끝난 상태이므로 순서와 무관하게 같은
        # 주제의 confirmed 사실이 하나라도 있으면(같은 논의를 다른 대안으로 확정) 대체된 것으로 본다.
        if fact.status in {"proposed", "unresolved"}:
            superseded_by_confirmation = any(
                later.status == "confirmed"
                and later.source_order >= fact.source_order
                and related(fact.topic, f"{fact.topic} {fact.content}", f"{later.topic} {later.content}")
                for later in fact_index.facts
                if later is not fact
            )
        elif fact.status == "rejected":
            superseded_by_confirmation = any(
                later.status == "confirmed"
                and related(fact.topic, f"{fact.topic} {fact.content}", f"{later.topic} {later.content}")
                for later in fact_index.facts
                if later is not fact
            )
        else:
            superseded_by_confirmation = False
        promoted_decision = bool(decision_section) and any(
            related(fact.topic, f"{fact.topic} {fact.content}", item)
            for item in decision_section.items
        )
        exclusion_decision = bool(decision_section) and any(
            related(fact.topic, f"{fact.topic} {fact.content}", item)
            and re.search(r"제외|채택하지|중단|철회|이관", item)
            for item in decision_section.items
        )
        if (
            fact.status in {"proposed", "unresolved", "rejected"}
            and not superseded_by_confirmation
            and promoted_decision
            and not (fact.status == "rejected" and exclusion_decision)
        ):
            issues.append(QualityIssue(
                "non_confirmed_as_decision",
                f"{fact.status} 상태의 '{fact.topic}'이 최종 결정 근거로 사용됨",
                "blocking", "decisions",
            ))
        rejected_feature = bool(feature_section) and any(
            related(fact.topic, f"{fact.topic} {fact.content}", f"{feature.title} {feature.description}")
            and quotes & {_normalize(item.quote) for item in feature.evidence}
            for feature in feature_section.features
        )
        if fact.status == "rejected" and rejected_feature and not superseded_by_confirmation:
            issues.append(QualityIssue(
                "rejected_as_feature",
                f"제외된 '{fact.topic}'이 주요 기능 근거로 사용됨",
                "blocking", "features",
            ))

    return QualityReport(issues)


@dataclass(frozen=True)
class GoldenExpectation:
    expectation_id: str
    section: str
    term_groups: tuple[tuple[str, ...], ...]
    area: Literal["body", "review", "all"] = "body"


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    source_file: str
    required: tuple[GoldenExpectation, ...]
    forbidden: tuple[GoldenExpectation, ...]


@dataclass(frozen=True)
class GoldenResult:
    case_id: str
    required_total: int
    required_matched: int
    missing_ids: tuple[str, ...]
    forbidden_ids: tuple[str, ...]

    @property
    def recall(self) -> float:
        return self.required_matched / self.required_total if self.required_total else 1.0

    @property
    def passed(self) -> bool:
        return not self.missing_ids and not self.forbidden_ids


def _load_expectation(raw: dict) -> GoldenExpectation:
    return GoldenExpectation(
        expectation_id=raw["id"],
        section=raw["section"],
        term_groups=tuple(tuple(group) for group in raw["term_groups"]),
        area=raw.get("area", "body"),
    )


def load_golden_cases(path: Path) -> list[GoldenCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [GoldenCase(
        case_id=item["case_id"],
        source_file=item["source_file"],
        required=tuple(_load_expectation(value) for value in item.get("required", [])),
        forbidden=tuple(_load_expectation(value) for value in item.get("forbidden", [])),
    ) for item in payload["cases"]]


def _matches(text: str, expectation: GoldenExpectation) -> bool:
    normalized = _normalize(text)
    return all(
        any(_normalize(term) in normalized for term in alternatives)
        for alternatives in expectation.term_groups
    )


_HEDGE_PATTERN = re.compile(
    r"검토|고민|할지|할까|해야\s*하나|필요할지|알아봐|계획\s*중|예정|보류|미정|미확정|"
    r"추가\s*논의|후속\s*논의|논의가?\s*필요|"
    r"제외|채택하지|하지\s*않는다|하지\s*않기로|배제|불가|이관|철회"
)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _matches_as_confirmed(text: str, expectation: GoldenExpectation) -> bool:
    """금지 앵커는 원문이 '검토 중'처럼 이미 미확정으로 남겨둔 문장까지
    확정 오류로 오탐하지 않도록, 같은 문장에 헤지 표현이 없을 때만 인정한다."""
    sentences = _sentences(text)
    if not sentences:
        return False
    return any(
        not _HEDGE_PATTERN.search(sentence) and _matches(sentence, expectation)
        for sentence in sentences
    )


def evaluate_golden(plan: PlanDocument, case: GoldenCase) -> GoldenResult:
    """표현 하나를 정답으로 고정하지 않고 의미 앵커 묶음의 충족을 평가합니다."""
    sections = {section.key: section for section in plan.sections}

    def target_text(item: GoldenExpectation) -> str:
        section = sections.get(item.section)
        if not section:
            return ""
        if item.area == "review":
            return section.needs_input
        if item.area == "all":
            return _plain_text(section)
        body = re.sub(
            r"<p><strong>PM 확인 사항</strong></p><ul>.*?</ul>\s*$",
            "", section.content_html or "", flags=re.DOTALL,
        )
        return " ".join(unescape(re.sub(r"<[^>]+>", " ", body)).split())

    missing = tuple(
        item.expectation_id for item in case.required
        if not _matches(target_text(item), item)
    )
    forbidden = tuple(
        item.expectation_id for item in case.forbidden
        if _matches_as_confirmed(target_text(item), item)
    )
    return GoldenResult(
        case_id=case.case_id,
        required_total=len(case.required),
        required_matched=len(case.required) - len(missing),
        missing_ids=missing,
        forbidden_ids=forbidden,
    )
