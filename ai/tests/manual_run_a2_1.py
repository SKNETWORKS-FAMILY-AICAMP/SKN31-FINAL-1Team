"""
tests/manual_run_a2_1.py

A2-1(요구사항정의서 생성)을 실제 LLM 호출까지 포함해 수동으로 실행해보는 스크립트.
test_a2_1.py는 LLM을 호출하지 않는 부분만 검증하므로, 실제 생성 결과를 눈으로
확인하려면 이 스크립트를 사용한다.

사전 준비:
  1. ai/.env 에 실제 OPENAI_API_KEY 값이 설정되어 있어야 한다.
  2. shared/retry_config.py의 DEFAULT_MODEL이 그 키로 실제 호출 가능한
     모델명인지 확인한다 (예: OpenAI 키라면 "gpt-4o-mini" 등).

실행:
  cd ai
  ../.venv/bin/python3 tests/manual_run_a2_1.py

  # fixture를 바꿔서 실행하고 싶으면:
  ../.venv/bin/python3 tests/manual_run_a2_1.py tests/fixtures/다른파일.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from requirement_draft.agent import generate_requirements
from requirement_draft.schemas import PlanDocument

DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "sample_plan_test.json"


def main() -> None:
    fixture_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FIXTURE

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    plan = PlanDocument.model_validate(data)

    print(f"[입력 기획서] {fixture_path} — {plan.title} ({len(plan.requirements)}개 요구사항 원문)\n", file=sys.stderr)

    result = generate_requirements(plan, plan_id="PLAN-TEST-001")

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    print(
        f"\n[요약] 총 {len(result.requirements)}건 생성 "
        f"(기능 {sum(1 for r in result.requirements if r.type.value == '기능')}건 / "
        f"비기능 {sum(1 for r in result.requirements if r.type.value == '비기능')}건)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
