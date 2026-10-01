"""기획서 생성 전략을 동일한 골든 기준으로 반복 비교합니다.

기본적으로 외부 API를 실제 호출하므로 명시한 사례만 실행합니다.

예시:
  python compare_plan_strategies.py --case vague_meeting --case musinsa_long \
      --strategy direct --strategy indexed --runs 1
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

AI_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=AI_DIR.parent / ".env")

from plan_draft.agent import run as generate_plan
from plan_draft.quality_gate import evaluate_golden, inspect_plan, load_golden_cases
from shared import llm_instrumentation


DEFAULT_GOLDEN = AI_DIR / "tests" / "fixtures" / "plan_quality_golden.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="기획서 생성 전략 품질·시간 비교")
    parser.add_argument("--case", action="append", required=True, dest="case_ids")
    parser.add_argument(
        "--strategy", action="append", choices=("parallel", "hybrid", "direct", "indexed"),
        dest="strategies", required=True,
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument(
        "--structured", type=Path,
        help="단일 case 실행 시 운영과 같은 회의록 구조화 JSON을 사용합니다.",
    )
    parser.add_argument("--output-dir", type=Path, default=AI_DIR / "out" / "quality_compare")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs는 1 이상이어야 합니다.")
    if args.structured and len(args.case_ids) != 1:
        parser.error("--structured는 --case 한 건과 함께 사용해야 합니다.")

    cases = {case.case_id: case for case in load_golden_cases(args.golden)}
    unknown = sorted(set(args.case_ids) - cases.keys())
    if unknown:
        parser.error(f"알 수 없는 case_id: {', '.join(unknown)}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for case_id in args.case_ids:
        case = cases[case_id]
        source_path = args.golden.parent / case.source_file
        source = source_path.read_text(encoding="utf-8")
        for strategy in args.strategies:
            for run_no in range(1, args.runs + 1):
                llm_instrumentation.clear_records()
                indexes = []
                stages = []
                started = time.perf_counter()
                structured = (
                    json.loads(args.structured.read_text(encoding="utf-8"))
                    if args.structured
                    else {
                        "meeting_id": f"BENCH-{case_id}",
                        "plan_source_text": source,
                        "project": {}, "users": [], "requirements": {},
                        "decisions": [], "constraints": [], "unresolved": [],
                    }
                )
                structured["plan_source_text"] = source
                plan = generate_plan(
                    structured,
                    proposal_id=f"BENCH-{case_id}-{strategy}-{run_no}",
                    generation_strategy=strategy,
                    on_fact_index=indexes.append,
                    on_stage=lambda label: stages.append({
                        "label": label,
                        "elapsed_seconds": round(time.perf_counter() - started, 3),
                    }),
                )
                elapsed = time.perf_counter() - started
                golden = evaluate_golden(plan, case)
                rules = inspect_plan(plan, source, indexes[0] if indexes else None)
                stem = f"{case_id}__{strategy}__{run_no}"
                plan_path = args.output_dir / f"{stem}.plan.json"
                plan_path.write_text(
                    json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                fact_index_path = args.output_dir / f"{stem}.facts.json"
                fact_index_path.write_text(
                    json.dumps(
                        (indexes[0].model_dump(mode="json") if indexes else {"facts": []}),
                        ensure_ascii=False, indent=2,
                    ),
                    encoding="utf-8",
                )
                row = {
                    "case_id": case_id,
                    "strategy": strategy,
                    "run": run_no,
                    "elapsed_seconds": round(elapsed, 3),
                    "required_recall": round(golden.recall, 4),
                    "missing_required": list(golden.missing_ids),
                    "matched_forbidden": list(golden.forbidden_ids),
                    "blocking_rule_issues": [issue.code for issue in rules.blocking_issues],
                    "passed": golden.passed and rules.passed,
                    "stage_timeline": stages,
                    "llm_calls": [
                        {
                            "context": metric.context,
                            "model": metric.model,
                            "duration_seconds": round(metric.duration_seconds, 3),
                            "attempt_count": metric.attempt_count,
                            "input_tokens": metric.input_tokens,
                            "output_tokens": metric.output_tokens,
                            "total_tokens": metric.total_tokens,
                            "success": metric.success,
                            "error_type": metric.error_type,
                        }
                        for metric in llm_instrumentation.get_records()
                    ],
                    "plan_path": str(plan_path),
                    "fact_index_path": str(fact_index_path),
                }
                results.append(row)
                print(json.dumps(row, ensure_ascii=False))

    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"결과 저장: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
