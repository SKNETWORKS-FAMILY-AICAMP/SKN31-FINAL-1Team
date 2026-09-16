"""a2_1_requirement_draft/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

from .schemas import PlanDocument

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def load_template() -> Dict[str, Any]:
    with open(PROMPT_DIR / "requirements_template.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_nfr_checklist() -> Dict[str, Any]:
    with open(PROMPT_DIR / "nfr_checklist.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_fr_decomposition_rules() -> Dict[str, Any]:
    with open(PROMPT_DIR / "fr_decomposition_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_priority_rules() -> Dict[str, Any]:
    with open(PROMPT_DIR / "priority_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_field_roles() -> Dict[str, Any]:
    with open(PROMPT_DIR / "field_roles.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_mandatory_labels() -> Dict[str, Any]:
    with open(PROMPT_DIR / "mandatory_labels.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_scope_guardrails() -> Dict[str, Any]:
    with open(PROMPT_DIR / "scope_guardrails.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _render_json(data: Dict[str, Any]) -> str:
    """조건-행동 매핑처럼 이미 구조가 명확한 규칙은 사람이 읽기 쉬운 불릿
    텍스트로 요약하지 않고 JSON 그대로 프롬프트에 주입한다 — 모델이 각
    조건-행동 쌍을 정확히 대응시키게 하기 위함이다(2026-09-15, 프롬프트
    규칙을 JSON 구조로 통일). nfr_checklist처럼 여러 필드를 사람이 읽기
    쉬운 설명으로 재구성해야 하는 경우만 별도 렌더러(_render_nfr_checklist)
    를 쓴다.

    indent 없는 compact 직렬화를 쓴다 — pretty-print의 들여쓰기 공백은
    모델의 파싱에 도움이 되지 않고 토큰만 소비한다(2026-09-15 실측:
    tiktoken cl100k_base 기준 이 5개 블록 합계가 pretty 3,128 토큰 →
    compact 2,649 토큰, 약 15% 절감). 사람이 읽을 원본은 소스 YAML
    파일에 이미 들여쓰기가 있으니 여기서 또 예쁘게 찍을 필요가 없다.
    """
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _render_scope_guardrails(data: Dict[str, Any]) -> str:
    """example_domain을 프롬프트 주입에서 제외한다.

    example_domain은 "재고관리 프로젝트에서는 이렇게 적용됐다"는 사람이
    읽는 문서화용 예시일 뿐, rule/action이 이미 일반화된 규칙이라 모델이
    매 호출마다 이 필드까지 받을 필요는 없다(2026-09-15 실측: 이 필드가
    scope_guardrails 블록 토큰의 상당 부분을 차지 — 제거로 가장 큰 절감
    효과). 소스 YAML(scope_guardrails.yaml)에는 유지해 사람이 규칙의
    유래를 계속 확인할 수 있게 한다.
    """
    trimmed = {
        "guardrails": [
            {k: v for k, v in g.items() if k != "example_domain"}
            for g in data.get("guardrails", [])
        ]
    }
    return _render_json(trimmed)


def _render_few_shots(examples: list) -> str:
    blocks = []
    for i, ex in enumerate(examples, start=1):
        blocks.append(
            f"[예시 {i}] {ex.get('description', '')}\n"
            f"입력:\n{json.dumps(ex['input'], ensure_ascii=False, indent=2)}\n"
            f"출력:\n{json.dumps(ex['output'], ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


def _render_nfr_checklist(checklist: Dict[str, Any]) -> str:
    lines = []
    all_categories = checklist.get("standard_categories", []) + checklist.get(
        "project_specific_categories", []
    )
    for cat in all_categories:
        mode_label = "[항상 생성]" if cat["generation_mode"] == "baseline" else "[조건부 생성]"
        example = cat.get("example", {})
        lines.append(
            f"- {cat['name_kr']} ({cat['id']}) {mode_label}\n"
            f"  하위특성: {', '.join(cat.get('sub_characteristics', []))}\n"
            f"  적용 조건: {cat.get('trigger_hint', '-')}\n"
            f"  예시 형식: {example.get('name', '')} — {example.get('description', '')}"
        )
    return "\n".join(lines)


def build_system_prompt(plan: PlanDocument) -> str:
    template = load_template()

    return f"""{template['role']}

{template['constraints']}

[필드별 역할 — JSON]
아래 fields 목록은 [기획서]의 각 필드를 FR/NFR 생성에서 어떤 역할로 쓸지
정의한다. role 값의 의미: FR_PRIMARY=FR의 주된 근거, NFR_PRIMARY=NFR의 주된
근거, FR_REFERENCE_ONLY=FR 서술에 참고만 하고 그 자체로 새 FR을 만들지 않음,
NARRATIVE_CONTEXT_ONLY=목표 서술 참고용(확정 요구로 바꾸지 않음),
TAG_GATED=tag_rules에 따라 갈림([범위] 태그 항목은 절대 요구사항화하지 않음).
{_render_json(load_field_roles())}

[범위·권한·미정 스펙 가드레일 — JSON]
각 guardrail의 rule/action은 모든 프로젝트에 적용되는 일반 규칙이다.
{_render_scope_guardrails(load_scope_guardrails())}

[기능요구사항(FR) 분해 규칙 — JSON]
아래 각 rule은 condition이 입력 기획서에 실제로 해당할 때만 action을 적용하라는
뜻이다. 여러 rule의 condition에 동시에 해당하면 그만큼 별도 FR로 분리할 수
있다. note에 적힌 대로, 근거 없이 개수만 채우려고 조건을 무리하게 적용하지 마라.
{_render_json(load_fr_decomposition_rules())}

[우선순위 판단 규칙 — JSON]
functional_rules는 순서대로 확인해 먼저 해당하는 조건의 priority를 쓴다.
non_functional_rules는 category_2(NFR 표준 카테고리명)로 매칭한다. 어느
규칙에도 확신 있게 해당하지 않으면 fallback을 따라 priority를 null로,
review_status를 검토대기로 설정한다.
{_render_json(load_priority_rules())}

[필수 여부 표기 기준 — JSON]
note에 필수 여부를 표시할 때는 아래 상태별 note_label을 그대로 쓴다. 필수
여부와 priority는 다른 개념이다 — 명시된 필수 폴백·디자인 기준은 priority가
Medium이어도 explicit_required로 표기한다.
{_render_json(load_mandatory_labels())}

[표준 비기능요구사항 체크리스트]
{_render_nfr_checklist(load_nfr_checklist())}

[출력 예시]
{_render_few_shots(template['few_shot_examples'])}

---
아래는 이번에 처리할 실제 기획서다. 위 규칙과 예시를 따라 요구사항정의서를 생성하라.

[기획서]
{json.dumps(plan.model_dump(exclude_none=True), ensure_ascii=False, indent=2)}
"""


def build_messages(plan: PlanDocument) -> list:
    return [
        {"role": "system", "content": build_system_prompt(plan)},
        {"role": "user", "content": "위 기획서를 바탕으로 요구사항정의서 초안을 생성하라."},
    ]
