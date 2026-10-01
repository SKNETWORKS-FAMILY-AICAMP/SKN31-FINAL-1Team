"""assignment_ranking/prompt_builder.py"""

import json
from typing import Any, Dict, List

_ROLES = "FRONTEND / BACKEND / DATA_ENGINEER / DEVOPS / UIUX_DESIGNER / QA_ENGINEER"


def build_split_prompt(packages: List[Dict[str, Any]], max_hours_per_assignee: float) -> str:
    return f"""너는 프로젝트의 기능 묶음(WorkPackage) 목록을 보고, 각 묶음을 한 담당자에게
통째로 맡기는 게 나은지 아니면 여러 담당자에게 나눠야 하는지 판단한다.

기본은 "한 사람에게 통째로"다 — 그래야 컨텍스트 스위칭이 줄고 책임이 명확하다.
아래에 해당할 때만 split=true로 하라:
  - 서로 다른 역할이 섞여 한 사람이 다 하기 어렵다 (예: 화면=FRONTEND 과 서버 API=BACKEND)
  - 한 사람의 기간 내 배정 상한({max_hours_per_assignee:.0f}시간)을 크게 넘는 분량이다
  - 독립적으로 병렬 진행 가능한 하위 기능들이고, 나누면 일정이 확실히 빨라진다

split=true일 때, 어느 unit끼리 묶여야 하는지 확신이 서면 unit_groups에 unit_id로
적어라(패키지의 모든 unit을 빠짐없이, 겹치지 않게). 애매하면 unit_groups를 비워라
— 코드가 요구사항/역할 기준으로 자동으로 나눈다.

reason은 PM이 읽을 한 문장으로 쓴다. split=false면 reason은 비워도 된다.

역할 코드: {_ROLES}

[기능 묶음 목록]
{json.dumps(packages, ensure_ascii=False, indent=2)}
"""


def build_candidate_fit_prompt(payload: List[Dict[str, Any]]) -> str:
    """
    2026-09-11: 업무별로 이미 스킬 기준으로 좁혀진 소수 후보의 경력기술서 원문·
    자격증·스킬 숙련도를 업무 설명과 대조해 질적 적합도를 판단시킨다.

    payload: [{"unit_id", "title", "description", "required_skills",
               "candidates": [{"employee_id", "skills_with_level", "certifications",
                                "career_history_tags"}, ...]}, ...]
    """
    return f"""너는 각 업무에 대해, 이미 기술 스택 기준으로 후보를 추려놓은 소수의
사원 중 누가 이 업무와 더 잘 맞는지 "내용"을 보고 판단한다. 최종 배정·용량 계산은
네 몫이 아니다 — 너는 오직 적합도 점수와 근거만 매긴다.

판단 기준:
  - 경력기술서에서 추출된 태그(career_history_tags)가 이 업무 설명과 실제로
    관련 있는지 봐라. "결제 연동 3건 경험"은 결제 업무엔 강한 근거지만 UI 업무엔
    약하다 — 개수가 아니라 내용의 관련성이 핵심이다.
  - 자격증이 이 업무 기술 스택과 직접 관련 있으면 가산, 무관하면 무시하라.
  - 스킬 숙련도(레벨)가 높을수록, 그리고 요구 스킬을 더 많이 커버할수록 높게 봐라.
  - 관련 경험이 전혀 없어도 0점을 주지 마라 — required_skills만 맞으면 최소한의
    수행은 가능하다는 뜻이니, 관련 경험이 없으면 낮은 점수(0.2~0.4대)를 줘라.

reason은 한 문장으로, 경력기술서의 구체적 내용을 인용해서 써라(예: "쇼핑몰
결제 시스템 구축 경험이 있어 PG 연동 업무와 직접 관련"). 입력받은 unit_id
전부와, 각 unit에 딸려온 후보 전원에 대해 빠짐없이 점수를 반환하라.

[업무·후보 목록]
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
