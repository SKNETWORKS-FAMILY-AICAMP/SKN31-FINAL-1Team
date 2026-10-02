"""Aggregate the three named 20-user, 300-second read runs from raw evidence."""
from pathlib import Path
import csv
import json
import math
import statistics
import argparse

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
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', nargs=3, default=RUNS)
    parser.add_argument('--output', default='repeat-summary-20u-5m')
    args = parser.parse_args()
    summaries = []
    all_rows = []
    for index, name in enumerate(args.runs, 1):
        folder = ROOT / "artifacts/load-test" / name
        manifest = json.loads((folder / "manifest.json").read_text())
        rows = list(csv.DictReader((folder / "requests.csv").open()))
        stage = manifest["stages"][0]
        assert manifest["status"] == "complete"
        assert manifest["concurrency"] == [20]
        assert manifest["duration_per_stage_seconds"] == 300
        assert len(rows) == stage["requests"]
        assert len({row["user"] for row in rows}) == 20
        errors = sum(row["status"] != "200" or row["valid"] != "True" for row in rows)
        assert errors == stage["errors"]
        values = [float(row["elapsed_ms"]) for row in rows]
        summary = {
            "repeat": index,
            "run_id": manifest["run_id"],
            "requests": len(rows),
            "errors": errors,
            "error_rate_pct": round(errors / len(rows) * 100, 3),
            "rps": round(len(rows) / stage["elapsed_seconds_including_drain"], 3),
            "mean_ms": round(statistics.fmean(values), 3),
            "p50_ms": percentile(values, 0.50),
            "p95_ms": percentile(values, 0.95),
            "p99_ms": percentile(values, 0.99),
            "max_ms": max(values),
        }
        endpoints = []
        for role, path in sorted({(r['role'], r['path']) for r in rows}):
            subset = [r for r in rows if r['role'] == role and r['path'] == path]
            endpoints.append({'role': role, 'path': path, 'requests': len(subset),
                              'errors': sum(r['valid'] != 'True' for r in subset),
                              'p95_ms': percentile([float(r['elapsed_ms']) for r in subset], .95)})
        summary['endpoints'] = endpoints
        summary['provisional_pass'] = (errors / len(rows) < .01 and
                                       all(x['p95_ms'] <= 1000 for x in endpoints))
        summary['counts'] = manifest['counts']
        summaries.append(summary)
        all_rows.extend(rows)

    p95_values = [item["p95_ms"] for item in summaries]
    rps_values = [item["rps"] for item in summaries]
    aggregate = {
        "runs": summaries,
        "total_requests": len(all_rows),
        "total_errors": sum(x['errors'] for x in summaries),
        "overall_error_rate_pct": round(sum(x['errors'] for x in summaries) / len(all_rows) * 100, 3),
        "mean_run_p95_ms": round(statistics.fmean(p95_values), 3),
        "run_p95_min_ms": min(p95_values),
        "run_p95_max_ms": max(p95_values),
        "run_p95_cv_pct": round(statistics.pstdev(p95_values) / statistics.fmean(p95_values) * 100, 2),
        "mean_rps": round(statistics.fmean(rps_values), 3),
        "rps_cv_pct": round(statistics.pstdev(rps_values) / statistics.fmean(rps_values) * 100, 2),
        "interpretation": (
            "Local read-only repeated runs; assess per-endpoint p95 and error rate separately. Not an AWS capacity result."
        ),
    }
    aggregate['all_runs_provisional_pass'] = all(x['provisional_pass'] for x in summaries)
    assert all(x['counts'] == summaries[0]['counts'] for x in summaries)
    output = ROOT / 'artifacts/load-test' / args.output
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

- 총 요청: {aggregate['total_requests']:,}건, 예상 밖 오류 {aggregate['total_errors']}건.
- 실행별 p95 평균: {aggregate['mean_run_p95_ms']:.1f}ms, 범위 {aggregate['run_p95_min_ms']:.1f}~{aggregate['run_p95_max_ms']:.1f}ms, 변동계수 {aggregate['run_p95_cv_pct']:.2f}%.
- 평균 처리량: {aggregate['mean_rps']:.2f} RPS, 실행 간 변동계수 {aggregate['rps_cv_pct']:.2f}%.
- 잠정 기준은 경로별 p95 1초 이내, 예상 밖 오류율 1% 미만이다. 전체 백분위만으로 경로별 통과를 판정하지 않는다.
- 세 회차 모두 경로별 잠정 기준 충족: {aggregate['all_runs_provisional_pass']}.
- 데이터 규모: {summaries[0]['counts']}.
- Gunicorn 워커 1개·gthread 2개, 로컬 MySQL, 사용자 20명, 300초, 요청 간 2~5초의 폐쇄형 모델이다.
- AI, 쓰기, Vercel, nginx, AWS 네트워크, DB 상세 계측은 포함하지 않았다. 운영 최대 용량 판정으로 사용하지 않는다.

각 실행의 원시 requests.csv, resources.csv, manifest.json은 해당 실행 폴더에 보존되어 있다.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
