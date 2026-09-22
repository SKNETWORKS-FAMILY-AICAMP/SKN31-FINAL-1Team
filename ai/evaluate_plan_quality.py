"""저장된 기획서 JSON을 골든 기준과 결정론적 품질 규칙으로 평가합니다.

예시:
  python evaluate_plan_quality.py \
    --plan out/plan_document_output.json \
    --source tests/fixtures/meeting_musinsa_long.txt \
    --case musinsa_long
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_draft.quality_gate import evaluate_golden, inspect_plan, load_golden_cases
from plan_draft.schemas import PlanDocument


DEFAULT_GOLDEN = Path(__file__).parent / "tests" / "fixtures" / "plan_quality_golden.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="기획서 골든 품질 평가")
    parser.add_argument("--plan", type=Path, required=True, help="PlanDocument JSON 경로")
    parser.add_argument("--source", type=Path, required=True, help="회의록 원문 경로")
    parser.add_argument("--case", required=True, help="골든 case_id")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    args = parser.parse_args()

    plan = PlanDocument.model_validate_json(args.plan.read_text(encoding="utf-8"))
    source = args.source.read_text(encoding="utf-8")
    cases = {case.case_id: case for case in load_golden_cases(args.golden)}
    if args.case not in cases:
        parser.error(f"알 수 없는 case_id: {args.case}. 선택값: {', '.join(sorted(cases))}")

    golden = evaluate_golden(plan, cases[args.case])
    rules = inspect_plan(plan, source)
    output = {
        "case_id": golden.case_id,
        "passed": golden.passed and rules.passed,
        "required_recall": round(golden.recall, 4),
        "missing_required": list(golden.missing_ids),
        "matched_forbidden": list(golden.forbidden_ids),
        "blocking_rule_issues": [
            {"code": issue.code, "section": issue.section_key, "message": issue.message}
            for issue in rules.blocking_issues
        ],
        "warnings": [
            {"code": issue.code, "section": issue.section_key, "message": issue.message}
            for issue in rules.issues if issue.severity == "warning"
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
