"""Aggregate the three named 20-user, 300-second read runs from raw evidence."""
from pathlib import Path
import csv
import json
import math
import statistics

ROOT = Path(__file__).resolve().parents[2]
RUNS = [
    "stages-20261001T032653Z",
    "stages-20261001T033916Z",
    "stages-20261001T034716Z",
]


def percentile(values, ratio):
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * ratio) - 1]


def main():
    summaries = []
    all_rows = []
    for index, name in enumerate(RUNS, 1):
        folder = ROOT / "artifacts/load-test" / name
        manifest = json.loads((folder / "manifest.json").read_text())
        rows = list(csv.DictReader((folder / "requests.csv").open()))
        stage = manifest["stages"][0]
        assert manifest["status"] == "complete"
        assert manifest["concurrency"] == [20]
        assert manifest["duration_per_stage_seconds"] == 300
        assert len(rows) == stage["requests"] == 1691
        assert len({row["user"] for row in rows}) == 20
        errors = sum(row["status"] != "200" or row["valid"] != "True" for row in rows)
        assert errors == stage["errors"] == 0
        values = [float(row["elapsed_ms"]) for row in rows]
        summary = {
            "repeat": index,
            "run_id": manifest["run_id"],
            "requests": len(rows),
            "errors": errors,
            "error_rate_pct": 0.0,
            "rps": round(len(rows) / stage["elapsed_seconds_including_drain"], 3),
            "mean_ms": round(statistics.fmean(values), 3),
            "p50_ms": percentile(values, 0.50),
            "p95_ms": percentile(values, 0.95),
            "p99_ms": percentile(values, 0.99),
            "max_ms": max(values),
        }
        summaries.append(summary)
        all_rows.extend(rows)

    p95_values = [item["p95_ms"] for item in summaries]
    rps_values = [item["rps"] for item in summaries]
    aggregate = {
        "runs": summaries,
        "total_requests": len(all_rows),
        "total_errors": 0,
        "overall_error_rate_pct": 0.0,
        "mean_run_p95_ms": round(statistics.fmean(p95_values), 3),
        "run_p95_min_ms": min(p95_values),
        "run_p95_max_ms": max(p95_values),
        "run_p95_cv_pct": round(statistics.pstdev(p95_values) / statistics.fmean(p95_values) * 100, 2),
        "mean_rps": round(statistics.fmean(rps_values), 3),
        "rps_cv_pct": round(statistics.pstdev(rps_values) / statistics.fmean(rps_values) * 100, 2),
        "interpretation": (
            "All three local read-only runs met the provisional p95 <= 1000 ms and "
            "unexpected error rate < 1% criteria. This is not an AWS capacity result."
        ),
    }
    output = ROOT / "artifacts/load-test/repeat-summary-20u-5m"
    output.mkdir(exist_ok=True)
    (output / "summary.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    table = "\n".join(
        f"| {item['repeat']} | {item['run_id']} | {item['requests']} | {item['errors']} | "
        f"{item['rps']:.2f} | {item['mean_ms']:.1f} | {item['p95_ms']:.1f} | "
        f"{item['p99_ms']:.1f} | {item['max_ms']:.1f} |"
        for item in summaries
    )
    readme = f"""# 20명·5분 일반 조회 3회 반복 결과

| 반복 | 실행 ID | 요청 | 오류 | RPS | 평균 ms | p95 ms | p99 ms | 최대 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
{table}

- 총 요청: {aggregate['total_requests']:,}건, 예상 밖 오류 0건.
- 실행별 p95 평균: {aggregate['mean_run_p95_ms']:.1f}ms, 범위 {aggregate['run_p95_min_ms']:.1f}~{aggregate['run_p95_max_ms']:.1f}ms, 변동계수 {aggregate['run_p95_cv_pct']:.2f}%.
- 평균 처리량: {aggregate['mean_rps']:.2f} RPS, 실행 간 변동계수 {aggregate['rps_cv_pct']:.2f}%.
- 세 실행 모두 로컬 조회 조건의 잠정 기준(p95 1초 이내, 예상 밖 오류율 1% 미만)을 충족했다.
- Gunicorn 워커 1개·gthread 2개, 로컬 MySQL, 사용자 20명, 300초, 요청 간 2~5초의 폐쇄형 모델이다.
- AI, 쓰기, Vercel, nginx, AWS 네트워크, DB 상세 계측은 포함하지 않았다. 운영 최대 용량 판정으로 사용하지 않는다.

각 실행의 원시 requests.csv, resources.csv, manifest.json은 해당 실행 폴더에 보존되어 있다.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
