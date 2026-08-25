"""
a2_3_assignee_recommend/rule_filter.py

기술스택·업무량 기반 1차 필터링. LLM 호출 이전에 코드로 후보를 좁힌다.
정확도가 중요한 부분(과부하 직원 배제 등)은 여기서 확정하고,
LLM에게는 "왜 적합한지" 서술만 맡긴다 (agent.py, prompt_builder.py 참고).
"""

from typing import Any, Dict, List

# TODO(담당자1): 팀 합의된 임계값으로 조정
MAX_CONCURRENT_TASKS = 3  # 이 이상 배정된 직원은 후보에서 제외


def filter_candidates(task: Dict[str, Any], members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Args:
        task: {"task_id", "task_type", "required_skills": [...], ...}
        members: member 테이블 조회 결과.
            [{"employee_id", "skills": [...], "current_task_count", "past_similar_tasks": [...]}]

    Returns:
        LLM에게 넘길 CandidateFeatures 리스트 (dict). 과부하 직원은 이미 제외됨.
    """
    candidates = []
    for m in members:
        # 규칙 1: 과부하 직원은 후보에서 완전히 제외 (LLM이 볼 수도 없게)
        if m["current_task_count"] >= MAX_CONCURRENT_TASKS:
            continue

        required = set(task.get("required_skills", []))
        matched = required & set(m.get("skills", []))
        if not matched:
            continue  # 규칙 2: 요구 기술과 하나도 안 맞으면 제외

        skill_ratio = len(matched) / len(required) if required else 0
        workload_score = 1 - (m["current_task_count"] / MAX_CONCURRENT_TASKS)
        similar_count = len(m.get("past_similar_tasks", []))

        rule_score = round(0.5 * skill_ratio + 0.3 * workload_score + 0.2 * min(similar_count / 3, 1), 2)

        candidates.append(
            {
                "employee_id": m["employee_id"],
                "skill_match": f"{'/'.join(matched)} 보유, 관련 업무 {len(m.get('past_similar_tasks', []))}건 수행",
                "workload": f"현재 할당 업무 {m['current_task_count']}건",
                "similar_experience": f"유사 업무 완료 이력 {similar_count}건",
                "rule_score": rule_score,
            }
        )

    candidates.sort(key=lambda c: c["rule_score"], reverse=True)
    return candidates[:3]  # 상위 3명만 LLM에게 근거 문장 생성 요청
