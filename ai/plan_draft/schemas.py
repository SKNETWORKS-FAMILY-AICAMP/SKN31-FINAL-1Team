"""
노드 ② 기획서 생성 스키마 — 7개 섹션.

## 섹션 구성

| 번호 | key        | 화면 제목                    | 생성 방식 |
|------|------------|------------------------------|-----------|
| 1    | overview   | 프로젝트 개요                | LLM       |
| 2    | problem    | 핵심 목표                    | LLM       |
| 3    | goals      | 세부 목표 및 문제 정의       | LLM + 코드 검증 |
| 4    | users      | 대상 사용자                  | LLM       |
| 5    | features   | 주요 기능                    | 코드      |
| 6    | tech_scope | 기술 스택 및 제약사항        | 코드      |
| 7    | decisions  | 최종 결정사항                | 코드      |

## PlanSections는 LLM이 생성하는 다음 결과를 담습니다.

    서술형 섹션:
        overview
        problem
        users

    구조화 배열:
        goals

주요 기능은 노드 1의 검증된 functional 요구사항을
feature_name 기준으로 코드가 조립합니다.

## 스키마가 두 개인 이유

PlanSections : LLM이 생성하는 서술형 3개와 조건부 목표
PlanDocument : 위 결과와 목록형 섹션 및 시스템 필드를 합친 최종 문서

is_incomplete 같은 시스템 필드를 LLM 스키마에 넣으면
모델이 "이것도 채워야 하나?" 하고 뭔가 써넣습니다.
아예 보여주지 않는 게 안전합니다.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas_base import Evidence, ReviewStatus


class SectionType(str, Enum):
    NARRATIVE = "narrative"   # LLM 작문
    LIST = "list"             # 코드 조립 — 재생성해도 같은 결과


# ─────────────────────────────────────────────────────────────
# 섹션 정의 — 이 표가 노드 ②의 설계도입니다.
# 프롬프트와 조립 코드 양쪽이 이걸 참조합니다.
# ─────────────────────────────────────────────────────────────
SECTION_SPEC = [
    {
        "no": 1,
        "key": "overview",
        "title": "프로젝트 개요",
        "type": SectionType.NARRATIVE,
        "source_fields": [
            "project.name",
            "project.background",
        ],
    },
    {
        "no": 2,
        "key": "problem",
        "title": "핵심 목표",
        "type": SectionType.NARRATIVE,
        "source_fields": [
            "project.name",
            "project.background",
            "project.problem",
            "project.problem_items",
            "project.goals",
        ],
    },
    {
        "no": 3,
        "key": "goals",
        "title": "세부 목표 및 문제 정의",
        "type": SectionType.LIST,
        "source_fields": [
            "project.problem",
            "project.problem_items",
            "project.goals",
        ],
    },
    {
        "no": 4,
        "key": "users",
        "title": "대상 사용자",
        "type": SectionType.NARRATIVE,
        "source_fields": ["users"],
    },
    {
        "no": 5,
        "key": "features",
        "title": "주요 기능",
        "type": SectionType.NARRATIVE,
        "source_fields": [
            "requirements.functional",
            "decisions[feature]",
        ],
    },
    {
        "no": 6,
        "key": "tech_scope",
        "title": "기술 스택 및 제약사항",
        "type": SectionType.LIST,
        "source_fields": [
            "requirements.technical",
            "requirements.non_functional",
            "requirements.data",
            "decisions[tech]",
            "constraints",
        ],
    },
    {
        "no": 7,
        "key": "decisions",
        "title": "최종 결정사항",
        "type": SectionType.LIST,
        "source_fields": ["decisions"],
    },
]

NARRATIVE_KEYS = [s["key"] for s in SECTION_SPEC if s["type"] == SectionType.NARRATIVE]
LIST_KEYS = [s["key"] for s in SECTION_SPEC if s["type"] == SectionType.LIST]


class Feature(BaseModel):
    """
    기획서 5번 주요 기능의 항목 하나.

    상세 정보가 없는 기능은 짧게 설명합니다.

    2026-09-14: group을 추가했습니다. 확정 기능 목록과 목록과 별개로
    확정된 연동을 화면에서 나눠 보여주기 위해서입니다. 원래는
    list_builder.build_features가 quote 열거 패턴으로 mvp/integration을
    판정했지만, 2026-09-15에 기능 작성 자체가 LLM 직접 작성 방식으로
    바뀌면서 build_features가 죽은 코드가 됐습니다(2026-09-17 삭제).

    2026-09-17: 그래서 지금 이 필드는 LLM 규칙(plan_generation.yaml
    features_rules)이 항상 "mvp"로만 쓰게 고정돼 있고, integration을
    실제로 재판정하는 코드는 없습니다. 나중에 이 구분이 다시 필요하면
    LLM 직접 작성 방식에 맞는 새 판정 로직을 설계해야 합니다.

    2026-09-16: source_indices를 추가했습니다. 예전엔 verified 항목만
    걸러 LLM에게 보여줬는데(prompts.py._verified_only), 그러면 근거
    검증에 실패한 진짜 기능이 LLM 눈에 보이지도 않고 조용히 사라졌습니다
    (6·7번에서 이미 확인된 것과 같은 침묵 실패). 이제 검증 여부와 무관하게
    번호만 매겨 전부 보여주고(feature_sources_for_citation), LLM은 몇 번을
    참고했는지만 답합니다. agent.py가 그 번호들의 실제 검증 상태를 코드로
    확인해 unverified가 섞여 있으면 표시를 붙입니다 — DetailedGoal의
    matched_goal_index와 같은 원리입니다.

    2026-09-17: model_config에 extra="forbid"를 추가했습니다. 필드가
    바뀔 때(예: problem_evidence/goal_evidence 삭제) 퓨샷 예시가 옛
    필드를 계속 들고 있어도 pydantic 기본 동작(extra 무시)으로는
    검증을 그냥 통과해 계약 불일치가 조용히 남습니다. forbid로 바꿔
    옛 필드가 남아 있으면 퓨샷 검증(prompt_loader._validate_example)이
    바로 실패하게 합니다.
    """

    model_config = ConfigDict(extra="forbid")

    group: Literal["mvp", "integration"] = Field(
        default="mvp",
        description=(
            "확정 기능 목록에 포함되면 mvp, "
            "목록과 별개로 확정된 연동이면 integration."
        ),
    )

    title: str = Field(
        ...,
        max_length=40,
        description=(
            "입력에서 확인되는 기능명. 30자 이내로 작성합니다. "
            "입력에 없는 기능을 만들지 않습니다."
        ),
    )

    description: str = Field(
        ...,
        description=(
            "검증된 기능 요구사항과 동일 원문에 연결된 결정사항으로 조립한 설명. "
            "세부 동작, 계산 기준, 적용 대상, 제외 범위와 필수 조건을 보존하며 "
            "입력에 없는 효과나 기능 관계는 포함하지 않습니다."
        ),
    )

    source_indices: list[int] = Field(
        default_factory=list,
        description=(
            "이 기능을 작성할 때 참고한 feature_sources_for_citation의 "
            "번호들. 여러 항목을 묶었으면 전부 나열합니다."
        ),
    )

    review_questions: list[str] = Field(
        default_factory=list,
        description=(
            "기능 설명 본문에 경고를 붙이지 않고 섹션 하단에서 PM에게 확인할 "
            "구체적인 질문. 질문이 없으면 빈 배열입니다."
        ),
    )


class NarrativeSection(BaseModel):
    """
    LLM이 생성하는 서술형 섹션.

    2026-09-16: "원본이 비어 있으면 무조건 빈 문자열"이었던 규칙을
    완화했습니다. 원본이 전혀 없어도 프로젝트의 다른 확인된 내용으로
    합리적으로 추정 가능하면 짧은 제안 초안을 씁니다(plan_generation.yaml
    common_rules 참고). 이 문단이 실제 회의 근거로 채워졌는지 AI가
    추정한 것인지는 LLM의 자기 신고가 아니라 agent.py가
    _source_is_empty()로 판정해 표시를 붙입니다 — evidence_status를
    LLM이 아니라 코드가 판정하는 것과 같은 이유입니다.

    2026-09-17: source_indices를 추가했습니다. 4번 대상 사용자 전용으로
    씁니다 — users 배열에 이미 실제 사용자가 있어도 니즈가 한두 줄뿐이라
    화면이 얇아 보이는 문제가 있었습니다(예: "최저가를 고른다" 한 줄).
    user_sources_for_citation(검증된 requirements.functional·
    requirements.data)에서 그 사용자와 명백히 관련된 항목을 인용해
    설명을 보완할 수 있게 하고, 실제로 어떤 번호를 참고했는지 여기 답하게
    합니다. Feature.source_indices와 같은 원리로, agent.py가 이 번호가
    실제로 있는지 코드로 확인해 보완 여부를 판정합니다 — LLM이 "이건
    추정입니다"라고 스스로 밝히게 하지 않습니다. overview·problem
    섹션은 이 필드를 쓰지 않으므로 빈 배열로 둡니다.
    """
    key: str
    content_html: str = Field(
        ...,
        description=(
            "원본이 있으면 그 내용을 씁니다. 원본이 전혀 없으면 다른 확인된 "
            "내용으로 합리적으로 추정되는 경우에만 짧게 제안하고, 그마저 "
            "없으면 빈 문자열."
        ),
    )
    evidence: list[Evidence] = Field(default_factory=list)
    source_indices: list[int] = Field(
        default_factory=list,
        description=(
            "users 섹션 전용. 설명을 보완하려고 user_sources_for_citation에서 "
            "참고한 항목의 번호. overview·problem 섹션은 항상 빈 배열입니다."
        ),
    )

    # 반려 사유를 다 반영하지 못했을 때 그 이유를 적습니다.
    #
    # 재생성을 요청받았는데 원본에 정보가 없으면 지어내는 대신
    # "무엇이 없어서 못 채웠는지"를 여기 적게 합니다.
    # 이게 없으면 작성자는 반려했는데 결과가 그대로인 이유를 알 수 없습니다.
    needs_input: str = Field(
        default="",
        description=(
            "반려 사유 중 원본 정보가 없어 반영하지 못한 부분. "
            "전부 반영했으면 빈 문자열."
        ),
    )

class DetailedGoal(BaseModel):
    """
    기획서의 세부 목표 및 문제 정의 항목.

    2026-09-15: problem_evidence·goal_evidence 필드를 없앴습니다.
    예전엔 이 필드에 담긴 quote가 노드①의 검증된 quote와 문자 그대로
    일치해야만(list_builder.build_goals) 항목이 채택됐는데, LLM이 문제와
    목표를 자기 말로 정리하면서 quote를 조금만 바꿔도 탈락해 항목이 거의
    안 남았습니다. 이제 이 섹션의 근거는 project.problem_items·
    project.goals의 검증된 quote를 통째로(항목별 매칭 없이) 보여줍니다
    (list_builder.build_goals, collect_source_evidence 참고) — 6·7번과
    같은 방식입니다.

    2026-09-16: matched_goal_index를 추가했습니다. goal 필드는 여전히
    LLM이 자기 말로 씁니다 — "이 문제와 project.goals의 몇 번이 대응하는가"는
    문장 인용보다 훨씬 간단하고 검증하기 쉬운 객관식 판단이라, LLM에게
    번호만 답하게 하고 실제 채택 여부와 근거 연결은 코드가 결정합니다
    (list_builder.build_goals 참고). 번호가 유효하면 화면에 표시되는
    goal 문장 자체를 project.goals의 원문으로 코드가 덮어씁니다 — LLM이
    옮겨 적다 생기는 오차(예: "깔끔"→"깔끗") 위험이 이 경로에는 없습니다.
    번호가 없거나 범위를 벗어나면 이 goal 필드 값을 그대로 쓰되 "AI 제안"으로
    표시합니다.

    2026-09-17: matched_problem_index를 추가했습니다. goal과 같은 이유로,
    problem 필드도 project.problem_items를 LLM이 자기 말로 옮기면서
    표현이 조금씩 달라져 quote 완전 일치로는 어떤 problem_item과
    대응하는지 코드가 확인할 수 없었습니다. 그러면 노드①이 그 항목에
    붙인 context_flag(사실 검토 경고)를 problem 문장에 이어 붙일
    근거가 없어져 경고가 조용히 사라집니다. matched_goal_index와 같은
    방식으로 problem_sources_for_citation의 번호만 답하게 하고, 번호가
    유효하면 code가 problem 문장을 원문으로 덮어쓰며 그 항목의
    context_flag도 함께 적용합니다(list_builder.build_goals 참고).

    2026-09-17: model_config에 extra="forbid"를 추가했습니다. Feature와
    같은 이유입니다(위 Feature 클래스 주석 참고) — problem_evidence·
    goal_evidence처럼 삭제된 필드가 퓨샷에 남아 있어도 조용히 통과하는
    문제를 막습니다.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        max_length=60,
        description="해결하려는 문제와 목표를 요약한 짧은 항목 제목",
    )

    problem: str = Field(
        ...,
        min_length=1,
        description="회의록에서 확인된 현재 문제를 한 문장으로 작성",
    )

    goal: str = Field(
        ...,
        description=(
            "해당 문제를 개선하기 위한 목표를 한 문장으로 작성. "
            "matched_goal_index가 없고 보수적으로도 제안할 근거가 없으면 "
            "빈 문자열로 둡니다(2026-09-17: min_length 제약을 없앴습니다 — "
            "list_builder.build_goals가 빈 문자열을 '목표 미논의' 고정 "
            "문구로 대체합니다)."
        ),
    )

    matched_problem_index: Optional[int] = Field(
        default=None,
        description=(
            "이 problem 문장과 직접 대응하는 문제가 "
            "problem_sources_for_citation 목록에 있으면 그 index 번호. "
            "없으면 null."
        ),
    )

    matched_goal_index: Optional[int] = Field(
        default=None,
        description=(
            "이 문제와 직접 대응하는 목표가 goals_for_citation 목록에 있으면 "
            "그 index 번호. 없으면 null."
        ),
    )


class PlanSections(BaseModel):
    """LLM 응답 형태. Instructor의 response_model로 씁니다."""

    sections: list[NarrativeSection] = Field(..., min_length=1)

    # 2026-09-15: max_length=4였던 것을 없앴습니다.
    #
    # 문제-목표를 원문 quote 완전 일치로만 짝짓던 예전 방식(list_builder.
    # build_goals)이 회의록에 실제로 있는 문제·목표를 대부분 걸러내
    # 항목이 1개만 남는 경우가 잦았습니다(develop 브랜치와 비교 실측:
    # 우리 3번 345자 vs develop 1503자). 이제 문제-목표 연결은 LLM이
    # 직접 판단하고, 개수 제한 없이 회의에 실제로 있는 만큼 씁니다.
    goals: list[DetailedGoal] = Field(
        default_factory=list,
        description=(
            "세부 목표 및 문제 정의 항목. project.problem_items·project.goals에 "
            "있는 문제와 목표를 빠짐없이 정리합니다. 개수 제한은 없지만 "
            "입력에 없는 문제·목표를 만들지 않습니다."
        ),
    )

    # 2026-09-15 추가: 5번 주요 기능도 LLM이 직접 씁니다.
    #
    # 예전엔 노드①이 각 요구사항에 붙인 feature_name 태그를 기준으로
    # 코드가 기계적으로 묶었습니다(list_builder.build_features). 태그가
    # 청크마다 일관되지 않거나 없으면 "기타 기능 요구사항"이라는 뭉텅이로
    # 전부 쏟아져 들어가는 문제가 실측으로 확인됐습니다. 검증된 기능
    # 요구사항·결정사항을 LLM에게 통째로 보여주고 직접 묶어 쓰게 하는 게
    # 더 안정적이었습니다(develop 브랜치 비교 실측).
    #
    # develop은 이 필드에 max_length=7을 걸어뒀는데, 그 캡 때문에 기능이
    # 많은 회의록(예: 9~10개 기능 영역)에서 일부가 통째로 빠지는 것도
    # 실측으로 확인했습니다. 그래서 여기는 상한을 두지 않습니다 — 회의에
    # 실제로 있는 기능은 다 씁니다.
    features: list[Feature] = Field(
        default_factory=list,
        description=(
            "주요 기능. 검증된 requirements.functional과 decisions[feature]를 "
            "의미 단위로 묶어서 작성합니다. 회의에 있는 기능은 개수 제한 없이 "
            "전부 포함합니다. 입력에 없는 기능을 만들지 않습니다."
        ),
    )


class Review(BaseModel):
    state: ReviewStatus = ReviewStatus.PENDING
    comment: Optional[str] = None
    reject_type: Optional[str] = None   # 사실 오류 / 내용 부족 / 표현 문제 / 회의록 자체 문제


class VerifiedEvidence(BaseModel):
    """
    저장·화면 표시용 근거. LLM 응답 스키마(NarrativeSection.evidence)와는 다른 모델입니다.

    NarrativeSection.evidence는 LLM이 스스로 "이게 근거예요"라고 내놓은 것이라
    원문과 실제로 대조된 적이 없습니다(자기 인용, 검증 안 됨). 반면 이 모델은
    노드①이 verify_and_mark()로 이미 원문 대조를 마친 근거를 코드가 그대로
    재사용해 채우는 것이라 status가 실제 검증 결과를 반영합니다.

    status에 default를 주지 않은 이유: 코드가 항상 명시적으로 채웁니다.
    LLM 스키마가 아니므로 "이것도 채워야 하나" 문제가 없습니다.
    """
    quote: str
    status: str  # "verified" | "unverified" — ai/meeting_analysis/validators/evidence.py 값과 동일


class TechScopeGroup(BaseModel):
    """
    6번(기술 및 제약사항) 전용 소제목 단위 묶음.

    2026-09-07 추가: 지금까지 items는 소제목 구분 없이 전부 하나로 flat하게
    담겨 있었습니다. 화면(읽기/수정)에서 "기술 스택 소제목 아래 항목들",
    "제약사항 소제목 아래 항목들"처럼 구분해서 보여주고 편집하려면 이 구분이
    필요합니다 — content_html을 HTML로 렌더링하는 대신 구조 그대로 저장·표시
    하기로 한 결정에 따른 것입니다(프론트 전달사항 문서 참고).

    회의에서 안 나온 소제목은 애초에 항목이 없으므로 groups 배열에도
    포함되지 않습니다(list_builder.build_tech_scope의 기존 동작과 동일).
    """
    subtitle: str
    items: list[str]


class PlanSection(BaseModel):
    """저장·전달용 최종 섹션 형태."""
    no: int
    key: str
    title: str
    section_type: SectionType
    content_html: str

    # 같은 내용의 태그 없는 배열.
    # 화면은 content_html, 하류 노드(③)는 items를 씁니다.
    # 서술형 섹션(문단)은 쪼갤 항목이 없어 빈 배열입니다.
    items: list[str] = Field(default_factory=list)

    source_fields: list[str] = Field(default_factory=list)

    # 2026-09-07: LLM이 자체 생성하는 NarrativeSection.evidence(Evidence, 검증 안 됨)를
    # 그대로 쓰지 않습니다. 대신 노드①이 이미 원문 대조를 마친 근거를 source_fields
    # 경로로 재수집합니다(list_builder.collect_source_evidence). 그래서 여기 타입은
    # status를 갖는 VerifiedEvidence입니다 — quote만 있는 Evidence가 아닙니다.
    evidence: list[VerifiedEvidence] = Field(default_factory=list)

    # 4번 주요 기능 전용. 다른 섹션은 빈 배열입니다.
    # 프론트가 항목 단위로 편집하고, 노드 ③이 파싱 없이 사용합니다.
    features: list[Feature] = Field(default_factory=list)

    # 6번 기술 및 제약사항 전용. 다른 섹션은 빈 배열입니다.
    # items를 소제목별로 묶은 것 — 프론트가 소제목 단위로 편집합니다.
    groups: list[TechScopeGroup] = Field(default_factory=list)

    # 반려 사유 중 반영하지 못한 부분 (재생성 시에만 채워짐)
    needs_input: str = ""

    # 아래 세 필드는 코드가 채웁니다. LLM이 건드리지 않습니다.
    is_incomplete: bool = False
    edited_by_pm: bool = False
    review: Review = Field(default_factory=Review)


class PlanDocument(BaseModel):
    proposal_id: str
    meeting_id: str
    status: str = "draft"          # draft | in_review | approved | rejected
    sections: list[PlanSection]
    unresolved: list[str] = Field(default_factory=list)
