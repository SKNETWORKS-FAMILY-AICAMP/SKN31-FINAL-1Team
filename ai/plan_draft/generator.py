"""원문 사실 인덱스와 1~7번 전체 기획서 작성 계약 및 결정적 렌더링."""

import json
import re
from html import escape
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from meeting_analysis.validators.evidence import is_quote_verified
from shared.schemas_base import Evidence
from .feature_renderer import render_features as render_feature_html
from .load_prompts import load_plan_template
from .schemas import Feature, PlanSection, SectionType, TechScopeGroup, VerifiedEvidence


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

IMPLEMENTATION_ONLY_FEATURE_TITLE_PATTERN = re.compile(
    r"원본(?:\s*데이터)?\s*(?:보관|보존)|원본.*(?:저장|보관|보존).*분리|"
    r"근거.*(?:보존|저장|적재)|"
    r"저장소\s*분리|스토리지\s*분리|테이블\s*(?:분리|설계)|"
    r"스키마\s*설계|학습\s*인프라|학습\s*데이터\s*(?:수집|구축|구성)|"
    r"데이터셋\s*(?:수집|구축|구성)|모델\s*선택"
)

_TOKEN_STOPWORDS = {
    "사항", "확인", "필요", "결정", "최종", "관련", "방향", "기준", "어떻게",
    "대한", "위해", "사용", "적용", "진행", "여부", "정도", "내용", "경우",
    "데이터", "사용자", "기능", "서비스", "기술", "소스", "지표", "모델", "방식",
    "범위", "정보", "외부", "내부", "주요", "활용", "확정하고", "확정할까요",
}
_DECISIVE_WORDS = re.compile(
    r"단일|통합|분리|확정|채택|제외|우선|한정|고정|구분\s*컬럼|하나의\s*테이블"
)
_TENTATIVE_ACTION = re.compile(r"후처리|교정|보정|대체|전환")
_TENTATIVE_LANGUAGE = re.compile(
    r"검토|고민|해야\s*하나|할지|할까|필요할|알아봐|계획|예정|싶"
)
_FEATURE_TECH_SENTENCE = re.compile(
    r"(?=.*(?:대표\s*용어|동의어|유사어))(?=.*테이블)(?=.*(?:ID|아이디))(?=.*연결).*|"
    r"(?:S3|RDS|오브젝트\s*스토리지|RunPod|GPU).*?(?:저장|적재|학습|배포|추론)|"
    r"(?:CLIP|클립|주클로|고클립).*?(?:모델|학습|성능|비교|대안|검토)"
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


class FeaturePlan(BaseModel):
    features: list[Feature] = Field(default_factory=list)


class CitedListItem(BaseModel):
    text: str
    evidence: list[Evidence] = Field(default_factory=list)


class TechGroupDraft(BaseModel):
    title: Literal["기술 구성", "데이터·저장 방침", "핵심 제약"]
    items: list[CitedListItem] = Field(default_factory=list)


class TechScopeDraft(BaseModel):
    groups: list[TechGroupDraft] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class DecisionItemDraft(BaseModel):
    category: Literal["feature", "non_functional", "data", "tech", "scope"]
    content: str
    rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class DecisionsDraft(BaseModel):
    items: list[DecisionItemDraft] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class TechnicalDecisionPlan(BaseModel):
    """전체 회의록에서 직접 작성하는 6·7번 전용 응답."""

    tech_scope: TechScopeDraft
    decisions: DecisionsDraft


class PlanningFact(BaseModel):
    """기획서 작성 전에 원문에서 확인한 하나의 사실 또는 논의 상태."""

    topic: str
    status: Literal["confirmed", "proposed", "unresolved", "rejected", "current_state"]
    content: str
    evidence: list[Evidence] = Field(default_factory=list)
    section_candidates: list[Literal[
        "overview", "problem", "goals", "users", "features", "tech_scope", "decisions"
    ]] = Field(default_factory=list)
    source_order: int = 0


class PlanningFactIndex(BaseModel):
    """길이와 형식에 관계없이 최종 작성기가 참고하는 간결한 원문 지도."""

    facts: list[PlanningFact] = Field(default_factory=list)
    missing_areas: list[str] = Field(default_factory=list)


class WholePlanDraft(BaseModel):
    """한 번의 문맥에서 1~7번 전체를 함께 작성한 구조화 초안. 운영 경로에서는
    쓰지 않는다(평가용 indexed/direct 전략 전용) — 2026-09-21 인수인계 문서
    참고. 운영 기본값은 parallel(호출 A: ContentPlanDraft, 호출 B:
    TechnicalDecisionPlan을 병렬 실행)이다."""

    context: ContextPlan
    features: FeaturePlan
    technical: TechnicalDecisionPlan


class ContentPlanDraft(BaseModel):
    """parallel 전략의 호출 A 응답 — 1~5번(개요·목표·세부목표·사용자·주요기능)만
    다룬다. 6~7번(기술·최종 결정)은 별도 호출 B(TechnicalDecisionPlan)가
    병렬로 맡는다."""

    context: ContextPlan
    features: FeaturePlan


SECTION_MODELS = {
    "overview": OverviewDraft,
    "problem": CoreGoalDraft,
    "goals": GoalsDraft,
    "users": UsersDraft,
}


def system_prompt(glossary_text: str = "") -> str:
    path = Path(__file__).parent / "prompt_templates" / "context_generation.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules["glossary_rules"] = load_plan_template()["glossary_rules"]
    rules["rules"] = [
        rule for rule in rules["rules"]
        if "overview, problem, goals, users와 features" not in str(rule)
        and "features의 각 항목" not in str(rule)
    ]
    rules["rules"].insert(0, "overview, problem, goals, users만 출력합니다.")
    rules.get("sections", {}).pop("features", None)
    return json.dumps(rules, ensure_ascii=False) + "\n용어집(참고 자료):\n" + glossary_text


def content_plan_system_prompt(glossary_text: str = "") -> str:
    """parallel 전략의 호출 A(1~5번) 시스템 프롬프트. 회의록 원문만 최종
    기준으로 사용하며, 6~7번(기술·최종 결정)은 별도 호출 B가 맡으므로
    여기서는 다루지 않는다 — 2026-09-21 인수인계 문서 6.2절 참고."""
    path = Path(__file__).parent / "prompt_templates" / "context_generation.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules["glossary_rules"] = load_plan_template()["glossary_rules"]
    rules["rules"] = list(rules["rules"]) + [
        "overview, problem, goals, users, features 전체를 포함한 ContentPlanDraft 하나로 반환합니다. "
        "기술 구성·데이터 방침·최종 결정(6~7번)은 별도 호출이 맡으므로 여기서 다루지 않습니다.",
        "서비스의 핵심 목적(주목적)과 그 목적을 위해 곁들여 쓰는 부가 활용·부가 목적을 구분해서 씁니다. "
        "부가 목적이 주목적처럼 보이도록 섞어 쓰지 않습니다.",
        "주요 기능에는 사용자·운영자에게 제공되는 제품 능력과 사용자 가치를 위해 시스템이 수행하는 핵심 처리만 둡니다.",
        "학습 데이터 수집·데이터셋 구축, 모델 학습·선택·배포, GPU, 저장소·테이블·스키마·ID 연결은 주요 기능이 아니므로 "
        "여기서는 다루지 않습니다(기술 구성·데이터 방침은 호출 B의 몫입니다).",
        "제안·조건부 대안·검토 중인 기준은 확정형 본문에서 제거하고, 실제 제품 범위를 막는 중요한 미결정만 "
        "review_questions에 남깁니다.",
    ]
    return json.dumps(rules, ensure_ascii=False) + "\n용어집(참고 자료):\n" + glossary_text


def content_plan_messages(source: str) -> list[dict]:
    return [{"role": "user", "content": "[회의록 원문]\n" + source.strip()}]


def technical_decision_system_prompt(glossary_text: str = "") -> str:
    """parallel 전략의 호출 B(6~7번) 시스템 프롬프트. technical_decisions.yaml을
    그대로 쓴다 — 회의록 전체를 직접 읽고 기술 구성·데이터 방침·최종 결정만
    작성하도록 이미 검증된 규칙이다(사실 인덱스나 1~5번 맥락에 의존하지 않는다)."""
    path = Path(__file__).parent / "prompt_templates" / "technical_decisions.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    return json.dumps(rules, ensure_ascii=False) + "\n용어집(참고 자료):\n" + glossary_text


def technical_decision_messages(source: str) -> list[dict]:
    return [{"role": "user", "content": "[회의록 원문]\n" + source.strip()}]


def fact_index_system_prompt() -> str:
    rules = {
        "role": "회의록에서 기획서 작성에 필요한 사실과 논의 상태를 색인하는 분석가",
        "rules": [
            "요약문이나 기획서를 쓰지 말고 PlanningFactIndex만 반환한다.",
            "프로젝트 목적, 문제, 사용자, 기능, 데이터, 기술·제약, 결정, 미결정과 철회를 빠짐없이 찾는다.",
            "앞선 제안이 뒤에서 수정·철회·확정되면 각각의 상태와 원문 순서를 보존한다.",
            "confirmed는 명시적 동의·채택·현재 실행 사실, proposed는 아이디어·계획, unresolved는 결론 없는 질문·비교, rejected는 제외·철회, current_state는 현재 현황에만 사용한다.",
            "content에는 원문의 의미만 간결하게 쓰고 새로운 사용자·기능·수치·이유를 만들지 않는다.",
            "evidence.quote는 원문에 연속으로 존재하는 문장을 수정하지 않고 그대로 복사한다.",
            "잘 정리된 회의록의 제목과 결정 목록은 그대로 활용하고 불필요하게 재해석하지 않는다.",
            "정보가 부족하면 missing_areas에 영역명만 남기고 내용을 추측하지 않는다.",
            "source_order는 해당 사실의 첫 근거가 등장한 순서대로 1부터 부여한다.",
        ],
    }
    return json.dumps(rules, ensure_ascii=False)


def fact_index_messages(source: str, chunk_no: int = 1, chunk_count: int = 1) -> list[dict]:
    return [{
        "role": "user",
        "content": f"[회의록 구간 {chunk_no}/{chunk_count}]\n" + source.strip(),
    }]


def whole_plan_system_prompt(glossary_text: str = "") -> str:
    """사실 인덱스를 탐색 지도로 사용해 1~7번 전체를 한 번에 작성합니다."""
    context_rules = yaml.safe_load(
        (Path(__file__).parent / "prompt_templates" / "context_generation.yaml")
        .read_text(encoding="utf-8")
    )
    technical_rules = yaml.safe_load(
        (Path(__file__).parent / "prompt_templates" / "technical_decisions.yaml")
        .read_text(encoding="utf-8")
    )
    section_contract = dict(context_rules.get("sections", {}))
    feature_contract = section_contract.pop("features", {})
    rules = {
        "role": "회의록 전체를 읽고 일관된 개발 기획서 1~7번을 작성하는 시니어 서비스 기획자",
        "objective": (
            "사실·결정 인덱스를 누락 방지용 탐색 지도로 사용하되 원문을 최종 기준으로 삼아, "
            "처음부터 섹션 관계와 중요도가 일관된 하나의 기획서를 작성한다."
        ),
        "rules": [
            "context, features, technical을 모두 포함한 WholePlanDraft를 한 번에 반환한다.",
            "사실 인덱스는 원문을 대체하지 않는다. 인덱스와 원문이 충돌하면 후속 발언을 포함한 원문 맥락을 따른다.",
            "회의록에 없는 기능, 사용자, 권한, KPI, 일정, 수치, 결정, 대체 규칙 또는 확인 질문을 만들지 않는다.",
            "evidence.quote는 회의록에 연속으로 존재하는 원문만 그대로 사용하며 요약하거나 이어 붙이지 않는다.",
            "프로젝트 개요와 핵심 목표는 목적·문제·성과를 설명하고 기능 목록이나 구현 상세를 반복하지 않는다.",
            "대상 사용자가 회의에서 서비스 타깃으로 직접 확정되지 않았다면 is_proposal=true로 둔다. 원문에 권한 구분 논의가 없으면 권한 확인 질문을 만들지 않는다.",
            "주요 기능에는 사용자·운영자에게 제공되는 제품 능력과 사용자 가치를 위해 시스템이 수행하는 핵심 처리만 둔다.",
            "학습 데이터 수집·데이터셋 구축, 모델 학습·선택·배포, GPU, 저장소·테이블·스키마·ID 연결은 주요 기능이 아니라 기술 구성 또는 데이터·저장 방침으로 옮긴다.",
            "기능 description의 첫 문장은 title의 핵심 동작을 입력·처리·결과 관점에서 설명해야 한다. 핵심 동작 없이 예외·후처리·검토 문장만 남은 기능은 근거를 이용해 설명을 복원하거나 삭제한다.",
            "기능 설명에서는 모델명·학습 환경·테이블 구조 같은 구현 문장을 제거하되, 기능의 핵심 동작과 확정된 적용 조건은 보존한다.",
            "제안·조건부 대안·검토 중인 기준은 확정형 본문에서 제거하고, 실제 제품 범위를 막는 중요한 미결정만 review_questions에 남긴다.",
            "같은 질문이나 이미 최종 결정된 사항을 묻는 질문은 제거한다.",
            "최종 결정은 대안 선택과 후속 동의를 함께 읽어 확정된 우선순위·보완 소스·제외 범위를 누락하지 않는다.",
            "사실 인덱스에서 status가 confirmed이고 section_candidates에 decisions가 포함된 항목은, 이미 다른 결정 문장에 그 내용이 흡수된 경우가 아니라면 decisions.items에서 빠뜨리지 않는다.",
            "전사 오류는 본문에서 문맥상 명확한 일반 표현으로 바로잡되 evidence.quote는 고치지 않는다.",
            "짧거나 정보가 부족한 회의록은 항목 수를 억지로 늘리지 말고 확인된 내용만 작성한다.",
            "잘 정리된 회의록은 명시된 기능·결정·미결정 구조와 우선순위를 보존한다.",
        ],
        "context_section_contract": section_contract,
        "feature_contract": feature_contract,
        "technical_decision_contract": {
            "tech_scope_rules": technical_rules.get("tech_scope_rules", []),
            "decision_rules": technical_rules.get("decision_rules", []),
        },
        "glossary": glossary_text,
    }
    return json.dumps(rules, ensure_ascii=False)


def whole_plan_messages(
    source: str,
    fact_index: PlanningFactIndex,
    include_full_source: bool = True,
) -> list[dict]:
    payload = {
        "source_mode": "full" if include_full_source else "verified_fact_excerpts",
        "meeting_source_text": source.strip() if include_full_source else "",
        "planning_fact_index": fact_index.model_dump(mode="json"),
    }
    return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def merge_verified_fact_indexes(
    indexes: list[PlanningFactIndex], source: str,
) -> PlanningFactIndex:
    """청크별 색인을 원문 인용 검증 후 순서대로 하나의 탐색 지도로 합칩니다."""
    facts: list[PlanningFact] = []
    seen: set[tuple[str, str, str]] = set()
    missing: list[str] = []
    source_order = 1
    for index in indexes:
        missing.extend(index.missing_areas)
        for fact in index.facts:
            evidence = [
                item for item in fact.evidence
                if is_quote_verified(item.quote, source)
            ]
            if not evidence:
                continue
            key = (fact.topic.strip(), fact.status, fact.content.strip())
            if key in seen:
                continue
            seen.add(key)
            facts.append(fact.model_copy(update={
                "evidence": evidence,
                "source_order": source_order,
            }))
            source_order += 1
    return PlanningFactIndex(
        facts=facts,
        missing_areas=list(dict.fromkeys(item.strip() for item in missing if item.strip())),
    )


def filter_nonfinal_outputs(
    draft: WholePlanDraft,
    fact_index: PlanningFactIndex,
) -> WholePlanDraft:
    """동일한 원문 근거가 명시적으로 미확정·제외인 결과를 본문에서 제거합니다."""
    statuses_by_quote: dict[str, set[str]] = {}
    for fact in fact_index.facts:
        for evidence in fact.evidence:
            key = re.sub(r"\s+", "", evidence.quote)
            if key:
                statuses_by_quote.setdefault(key, set()).add(fact.status)

    def statuses(evidence_items: list[Evidence]) -> set[str]:
        found: set[str] = set()
        for evidence in evidence_items:
            found.update(statuses_by_quote.get(re.sub(r"\s+", "", evidence.quote), set()))
        return found

    confirmed_texts = [
        f"{fact.topic} {fact.content}"
        for fact in fact_index.facts if fact.status in {"confirmed", "current_state"}
    ]

    kept_features = []
    removed_features = []
    for feature in draft.features.features:
        item_statuses = statuses(feature.evidence)
        confirmed_same_topic = any(
            _same_topic(feature.title, text) for text in confirmed_texts
        )
        if (
            item_statuses
            and item_statuses <= {"proposed", "unresolved", "rejected"}
            and not confirmed_same_topic
        ):
            removed_features.append(feature.title.strip())
        else:
            kept_features.append(feature)

    kept_decisions = []
    removed_decisions = []
    for item in draft.technical.decisions.items:
        item_statuses = statuses(item.evidence)
        if (
            item_statuses
            and "confirmed" not in item_statuses
            and item_statuses & {"proposed", "unresolved", "rejected"}
        ):
            removed_decisions.append(item.content.strip())
        else:
            kept_decisions.append(item)

    # 명시적으로 제외하기로 정리한 범위도 중요한 최종 결정이다. 작성기가
    # 누락했을 때만 검증된 rejected 사실에서 복원한다.
    for fact in fact_index.facts:
        evidence_text = " ".join(item.quote for item in fact.evidence)
        if (
            fact.status != "rejected"
            or "decisions" not in fact.section_candidates
            or not re.search(r"제외|채택하지|중단|철회|2차.*이관", evidence_text)
            or any(_same_topic(fact.content, item.content) for item in kept_decisions)
        ):
            continue
        kept_decisions.append(DecisionItemDraft(
            category="scope",
            content=fact.content.strip(),
            evidence=fact.evidence,
        ))

    questions = list(draft.technical.decisions.review_questions)
    questions.extend(
        f"'{content}'은 회의에서 최종 확정되지 않았으므로 적용 여부를 확인해 주세요."
        for content in removed_decisions if content
    )
    questions.extend(
        f"회의에서 제외된 기능이므로 주요 기능에서 제거했습니다: {title}"
        for title in removed_features if title
    )
    return draft.model_copy(update={
        "features": draft.features.model_copy(update={"features": kept_features}),
        "technical": draft.technical.model_copy(update={
            "decisions": draft.technical.decisions.model_copy(update={
                "items": kept_decisions,
                "review_questions": list(dict.fromkeys(questions)),
            }),
        }),
    })


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


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[가-힣A-Za-z0-9]+", text or "")
        if len(token) >= 2 and token not in _TOKEN_STOPWORDS
    }


def _same_topic(left: str, right: str) -> bool:
    common = _tokens(left) & _tokens(right)
    return len(common) >= 2 or any(len(token) >= 3 for token in common)


def _user_has_direct_evidence(user: UserDraft) -> bool:
    """근거 원문이 사용자 역할을 직접 언급하는지 보수적으로 판정합니다."""
    generic_role_words = {"사용자", "담당자", "일반", "대상", "운영", "분석", "시장"}
    role_tokens = _tokens(user.name) - generic_role_words
    evidence_tokens = _tokens(" ".join(item.quote for item in user.evidence))
    return bool(role_tokens & evidence_tokens)


def _remove_review_html(content: str) -> str:
    return re.sub(
        r"<p><strong>PM 확인 사항</strong></p><ul>.*?</ul>\s*$",
        "",
        content or "",
        flags=re.DOTALL,
    )


def _sanitize_feature(feature: Feature) -> Feature:
    """검토 단계의 하위 동작과 기능에 섞인 저장·스키마 문장을 제거합니다."""
    relevant_quotes = [
        item.quote for item in feature.evidence if _TENTATIVE_ACTION.search(item.quote)
    ]
    tentative_only = bool(relevant_quotes) and all(
        _TENTATIVE_LANGUAGE.search(quote) for quote in relevant_quotes
    )

    sentences = re.split(r"(?<=[.!?])\s+", feature.description.strip())
    kept_sentences = [
        sentence for sentence in sentences
        if not _FEATURE_TECH_SENTENCE.search(sentence)
        and not (tentative_only and _TENTATIVE_ACTION.search(sentence))
    ]
    title = feature.title.strip()
    if tentative_only and _TENTATIVE_ACTION.search(title):
        title = re.sub(
            r"\s*(?:및|·|/)\s*[^·/]*(?:후처리|교정|보정|대체|전환).*$",
            "",
            title,
        ).strip()
    return feature.model_copy(update={
        "title": title,
        "description": " ".join(kept_sentences).strip(),
    })


def reconcile_sections(
    sections: list[PlanSection],
    decisions: DecisionsDraft,
) -> list[PlanSection]:
    """최종 결정을 기준으로 확정/미확정 충돌과 중복 질문을 정리합니다.

    추가 LLM 호출 없이 구조화된 결정 결과만 사용합니다. 확정 결정과 같은 주제의
    질문은 제거하고, 결정 섹션에 이미 남은 미확정 질문과 충돌하는 단정적인 기능
    문장은 삭제합니다. 질문은 결정→기술→기능→나머지 순으로 한 곳에만 남깁니다.
    """
    confirmed = [
        " ".join(filter(None, [item.content.strip(), item.rationale.strip()]))
        for item in decisions.items
        if item.content.strip()
    ]
    pending = [q.strip() for q in decisions.review_questions if q.strip()]

    feature_section = next((s for s in sections if s.key == "features"), None)
    if feature_section:
        cleaned_features: list[Feature] = []
        for feature in feature_section.features:
            kept_sentences = []
            for sentence in re.split(r"(?<=[.!?])\s+", feature.description.strip()):
                conflicts = any(_same_topic(sentence, question) for question in pending)
                if conflicts and _DECISIVE_WORDS.search(sentence):
                    continue
                kept_sentences.append(sentence)
            description = " ".join(kept_sentences).strip()
            if not description:
                description = feature.description
            questions = [
                q for q in feature.review_questions
                if not any(_same_topic(q, decision) for decision in confirmed)
            ]
            cleaned_features.append(feature.model_copy(update={
                "description": description,
                "review_questions": questions,
            }))
        feature_section.features = cleaned_features
        feature_section.items = [feature.title for feature in cleaned_features]
        feature_section.content_html = render_feature_html(
            cleaned_features,
            [q for feature in cleaned_features for q in feature.review_questions],
        )
        feature_section.needs_input = "\n".join(dict.fromkeys(
            q for feature in cleaned_features for q in feature.review_questions
        ))

    # 사용자·타깃·권한 질문은 다른 섹션 초안에서 발생해도 4번으로 모읍니다.
    users_section = next((s for s in sections if s.key == "users"), None)
    if users_section:
        moved_user_questions: list[str] = []
        for section in sections:
            if section.key == "users":
                continue
            questions = [q.strip() for q in section.needs_input.splitlines() if q.strip()]
            kept = []
            for question in questions:
                if re.search(r"사용자|타깃|고객|권한", question):
                    moved_user_questions.append(question)
                else:
                    kept.append(question)
            if len(kept) != len(questions):
                section.needs_input = "\n".join(kept)
                section.content_html = _remove_review_html(section.content_html) + _review_html(kept)
        if moved_user_questions:
            current = [q.strip() for q in users_section.needs_input.splitlines() if q.strip()]
            users_section.needs_input = "\n".join(dict.fromkeys(current + moved_user_questions))
            users_section.content_html = (
                _remove_review_html(users_section.content_html)
                + _review_html(current + moved_user_questions)
            )

    priority = {"decisions": 0, "tech_scope": 1, "features": 2,
                "users": 3, "goals": 4, "problem": 5, "overview": 6}
    seen_questions: list[str] = []
    for section in sorted(sections, key=lambda s: priority.get(s.key, 99)):
        questions = [q.strip() for q in section.needs_input.splitlines() if q.strip()]
        kept = []
        for question in questions:
            if any(_same_topic(question, decision) for decision in confirmed):
                continue
            if any(_same_topic(question, previous) for previous in seen_questions):
                continue
            kept.append(question)
            seen_questions.append(question)
        section.needs_input = "\n".join(kept)
        section.content_html = _remove_review_html(section.content_html) + _review_html(kept)
    return sections


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
        normalized_users = [
            user.model_copy(update={
                "is_proposal": user.is_proposal or not _user_has_direct_evidence(user),
            })
            for user in section.users
        ]
        confirmed_users = [user for user in normalized_users if not user.is_proposal]
        proposed_users = [user for user in normalized_users if user.is_proposal]
        grouped_users = []
        if confirmed_users and proposed_users:
            grouped_users.extend([("확인된 사용자", confirmed_users), ("제안 사용자", proposed_users)])
        elif proposed_users:
            grouped_users.append(("제안 사용자", proposed_users))
        else:
            grouped_users.append(("", confirmed_users))
        for group_title, users in grouped_users:
            if group_title:
                parts.append(f"<p><strong>{group_title}</strong></p>")
            for user in users:
                if not user.name.strip() or not user.description.strip():
                    continue
                if not _verified_evidence(user.evidence, source, evidence):
                    notes.append(f"{user.name} 사용자 설명의 근거를 회의록 원문과 대조해 확인해 주세요.")
                parts.append(f"<p><strong>{escape(user.name.strip())}</strong></p>")
                parts.append(f"<p>{escape(user.description.strip())}</p>")
                if user.usage.strip():
                    parts.append(f"<p>{escape(user.usage.strip())}</p>")
        proposal_names = [user.name.strip() for user in proposed_users if user.name.strip()]
        has_group_question = any(
            "외부 사용자" in note or "사용자 후보" in note or "타깃" in note
            for note in notes
        )
        if proposal_names and not has_group_question:
            if len(proposal_names) == 1:
                name = proposal_names[0]
                notes.append(
                    f"{name}{_josa(name, '을', '를')} 서비스 대상 사용자로 정의할지 확인이 필요합니다."
                )
            else:
                notes.append(
                    "제안 사용자 후보(" + ", ".join(proposal_names)
                    + ")의 포함 여부와 1차 우선순위를 확인해 주세요."
                )
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


def render_features(features: list[Feature], source: str) -> PlanSection:
    """원문에서 직접 생성한 기능과 인용을 기존 5번 섹션 계약으로 변환합니다."""
    section_evidence: dict[str, VerifiedEvidence] = {}
    notes: list[str] = []
    verified_features: list[Feature] = []

    for raw_feature in features:
        feature = _sanitize_feature(raw_feature)
        if not feature.title.strip() or not feature.description.strip():
            continue
        if IMPLEMENTATION_ONLY_FEATURE_TITLE_PATTERN.search(feature.title):
            continue
        item_evidence: dict[str, VerifiedEvidence] = {}
        if not _verified_evidence(feature.evidence, source, item_evidence):
            notes.append(
                f"'{feature.title.strip()}' 기능의 작성 근거를 회의록 원문과 "
                "대조해 확인해 주세요."
            )
        section_evidence.update(item_evidence)
        notes.extend(feature.review_questions)
        verified_features.append(feature.model_copy(update={
            "evidence": [Evidence(quote=item.quote) for item in item_evidence.values()]
        }))

    content = render_feature_html(verified_features, notes)
    return PlanSection(
        no=5,
        key="features",
        title="주요 기능",
        section_type=SectionType.NARRATIVE,
        content_html=content,
        features=verified_features,
        items=[feature.title for feature in verified_features],
        source_fields=["plan_source_text"],
        evidence=list(section_evidence.values()),
        needs_input="\n".join(dict.fromkeys(note for note in notes if note.strip())),
        is_incomplete=not verified_features,
    )


def render_technical_sections(
    draft: TechnicalDecisionPlan,
    source: str,
) -> tuple[PlanSection, PlanSection]:
    """원문 전용 응답을 기존 프론트·하류 계약의 6·7번으로 변환합니다."""
    tech_evidence: dict[str, VerifiedEvidence] = {}
    tech_notes = list(draft.tech_scope.review_questions)
    tech_parts: list[str] = []
    tech_items: list[str] = []
    tech_groups: list[TechScopeGroup] = []

    for group in draft.tech_scope.groups:
        lines: list[str] = []
        for item in group.items:
            text = item.text.strip()
            if not text:
                continue
            if not _verified_evidence(item.evidence, source, tech_evidence):
                tech_notes.append(f"'{text}'의 작성 근거를 회의록 원문과 대조해 확인해 주세요.")
            lines.append(text)
        if not lines:
            continue
        tech_parts.append(
            f"<p><strong>{escape(group.title)}</strong></p><ul>"
            + "".join(f"<li>{escape(line)}</li>" for line in lines)
            + "</ul>"
        )
        tech_items.extend(lines)
        tech_groups.append(TechScopeGroup(subtitle=group.title, items=lines))

    tech_notes = list(dict.fromkeys(note.strip() for note in tech_notes if note.strip()))
    tech_body_exists = bool(tech_parts)
    tech_parts.append(_review_html(tech_notes))
    tech_section = PlanSection(
        no=6, key="tech_scope", title="기술 스택 및 제약사항",
        section_type=SectionType.LIST, content_html="".join(tech_parts),
        items=tech_items, groups=tech_groups, source_fields=["plan_source_text"],
        evidence=list(tech_evidence.values()), needs_input="\n".join(tech_notes),
        is_incomplete=not tech_body_exists,
    )

    decision_evidence: dict[str, VerifiedEvidence] = {}
    decision_notes = list(draft.decisions.review_questions)
    decision_groups: dict[str, list[str]] = {}
    decision_items: list[str] = []
    labels = {
        "feature": "기능", "non_functional": "비기능 요구사항",
        "data": "데이터", "tech": "기술", "scope": "범위",
    }
    subtitles = {
        "feature": "기능 관련 결정", "non_functional": "비기능 관련 결정",
        "data": "데이터 관련 결정", "tech": "기술 관련 결정",
        "scope": "범위 관련 결정",
    }

    for item in draft.decisions.items:
        content = item.content.strip()
        if not content:
            continue
        if not _verified_evidence(item.evidence, source, decision_evidence):
            decision_notes.append(f"'{content}'의 작성 근거를 회의록 원문과 대조해 확인해 주세요.")
        rendered = content + (
            f" (이유: {item.rationale.strip()})" if item.rationale.strip() else ""
        )
        decision_groups.setdefault(item.category, []).append(rendered)
        decision_items.append(f"[{labels[item.category]}] {rendered}")

    decision_parts = [
        f"<p><strong>{escape(subtitles[category])}</strong></p><ul>"
        + "".join(f"<li>{escape(line)}</li>" for line in lines)
        + "</ul>"
        for category, lines in decision_groups.items()
    ]
    decision_notes = list(dict.fromkeys(
        note.strip() for note in decision_notes if note.strip()
    ))
    decision_body_exists = bool(decision_parts)
    decision_parts.append(_review_html(decision_notes))
    decision_section = PlanSection(
        no=7, key="decisions", title="최종 결정사항",
        section_type=SectionType.LIST, content_html="".join(decision_parts),
        items=decision_items, source_fields=["plan_source_text"],
        evidence=list(decision_evidence.values()),
        needs_input="\n".join(decision_notes),
        is_incomplete=not decision_body_exists,
    )
    return tech_section, decision_section
