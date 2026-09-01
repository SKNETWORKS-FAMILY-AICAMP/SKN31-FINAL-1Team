"""
tests/manual_run_assignee_pipeline.py

A2-1 -> A2-2 -> 담당자 매핑 -> A2-3 전체 체인을 실제 LLM 호출까지 포함해
수동으로 실행해보는 스크립트. 백엔드 의존 입력(raw_employee_profiles,
current_workload, project_start_date/end_date)은 실제 DB가 아직 없어
mock 값으로 대신 채운다 — 실제 조회 로직이 준비되면 이 부분만 교체하면 된다.

사전 준비:
  1. ai/.env 에 OPENAI_API_KEY(필수), ANTHROPIC_API_KEY(선택, 폴백용) 설정
  2. shared/retry_config.py의 DEFAULT_MODEL이 실제 호출 가능한 모델인지 확인

실행:
  cd ai
  ../.venv/bin/python3 tests/manual_run_assignee_pipeline.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assignee_mapping.agent import assignee_mapping_node
from assignee_recommend.agent import assignee_recommend_node
from requirement_draft.agent import requirement_draft_node
from requirement_draft.schemas import PlanDocument
from task_generation.agent import task_generation_node

DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "sample_plan_test.json"

# ---- mock: 실제 DB 연동 전까지 사용할 값들 (백엔드 완료 시 이 블록만 교체) ----
MOCK_PARTICIPANT_COUNT = 3
MOCK_PROJECT_START_DATE = "2026-09-01"
MOCK_PROJECT_END_DATE = "2026-09-30"


def _mock_raw_employee_profiles(all_skills: list) -> list:
    return [
        {
            "employee_id": "EMP-001",
            "employee_no": "24001",
            "name": "김주현",
            "skills": all_skills,
            "certifications": [],
            "career_history_text": (
                "산책메이트와 유사한 반려동물 예약 서비스에서 "
                "Django REST API를 개발한 경험이 있습니다."
            ),
        },
        {
            "employee_id": "EMP-002",
            "employee_no": "24002",
            "name": "이수민",
            "skills": all_skills[:1] if all_skills else [],
            "certifications": [],
            "career_history_text": "",
        },
    ]


def main() -> None:
    fixture_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FIXTURE

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    plan = PlanDocument.model_validate(data).model_dump(mode="json")

    state = {"project_id": "PJT-100", "plan_id": "1", "plan": plan}

    def run(name: str, node_fn) -> None:
        result = node_fn(state)
        if result.get("error"):
            print(f"[{name}] 실패: {result['error']}", file=sys.stderr)
            sys.exit(1)
        state.update(result)

    # A2-1
    run("A2-1", requirement_draft_node)
    print(f"[A2-1] {len(state['requirement_doc']['requirements'])}건 요구사항 생성", file=sys.stderr)

    # A2-2 — participant_count는 호출부(Django)가 미리 채우는 값, 여기선 mock
    state["participant_count"] = MOCK_PARTICIPANT_COUNT
    run("A2-2", task_generation_node)
    print(f"[A2-2] {len(state['tasks'])}건 업무 생성", file=sys.stderr)

    # 담당자 매핑 — raw_employee_profiles는 호출부가 미리 채우는 값, 여기선 mock
    all_skills = sorted({s for t in state["tasks"] for s in t.get("required_skills", [])})
    state["raw_employee_profiles"] = _mock_raw_employee_profiles(all_skills)
    run("담당자 매핑", assignee_mapping_node)
    print(f"[담당자 매핑] {len(state['member_profiles'])}명 프로필 생성", file=sys.stderr)
    for p in state["member_profiles"]:
        print(f"   - {p['employee_id']} tags: {p['past_similar_tasks']}", file=sys.stderr)

    # A2-3 — current_workload/프로젝트 기간은 호출부가 채우는 값, 여기선 mock
    state["current_workload"] = {m["employee_id"]: 0.0 for m in state["raw_employee_profiles"]}
    state["project_start_date"] = MOCK_PROJECT_START_DATE
    state["project_end_date"] = MOCK_PROJECT_END_DATE
    run("A2-3", assignee_recommend_node)

    print(json.dumps(state["assignments"], ensure_ascii=False, indent=2))

    ok = sum(1 for a in state["assignments"] if not a["review_required"])
    hold = len(state["assignments"]) - ok
    print(f"\n[요약] 총 {len(state['assignments'])}건 (배정 {ok}건 / 보류 {hold}건)", file=sys.stderr)


if __name__ == "__main__":
    main()
