"""Profile selected API queries against the local load-test database only."""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.db import connection, reset_queries
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from projects.models import Project
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment


ENDPOINTS = [
    "/api/tasks/assignments/",
    "/api/requirements/",
    "/api/dashboard/overview/",
    "/api/dashboard/analytics/",
    "/api/projects/",
]


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "profile"
    cfg = connection.settings_dict
    if not (
        cfg["HOST"] == "127.0.0.1"
        and str(cfg["PORT"]) == "3307"
        and cfg["NAME"] == "heyzzabi_test"
    ):
        raise RuntimeError("Refusing non-local database target")

    counts = {
        "projects": Project.objects.count(),
        "tasks": TaskAssignment.objects.count(),
        "requirement_definitions": RequirementDefinition.objects.count(),
        "requirement_items": RequirementItem.objects.count(),
    }
    results = []
    password = os.environ.get("LOADTEST_PASSWORD", "LocalLoad2026!")
    with override_settings(ALLOWED_HOSTS=["testserver"]):
        client = APIClient()
        response = client.post(
            "/api/users/login/",
            {"username": "lt_small_001", "password": password},
            format="json",
        )
        response.raise_for_status = lambda: None
        if response.status_code != 200:
            raise RuntimeError(f"Login failed: {response.status_code}")

        for path in ENDPOINTS:
            warmup = client.get(path)
            if warmup.status_code != 200:
                raise RuntimeError(f"Warmup failed: {path} {warmup.status_code}")
            for sample in range(1, 6):
                # Keep each sample below Django's per-connection query-log cap.
                # Without this reset a later sample can be truncated by queries_limit.
                reset_queries()
                started = time.perf_counter()
                with CaptureQueriesContext(connection) as captured:
                    response = client.get(path)
                elapsed_ms = (time.perf_counter() - started) * 1000
                if response.status_code != 200:
                    raise RuntimeError(f"Request failed: {path} {response.status_code}")
                db_ms = sum(float(item.get("time", 0)) for item in captured.captured_queries) * 1000
                results.append(
                    {
                        "path": path,
                        "sample": sample,
                        "status": response.status_code,
                        "elapsed_ms": round(elapsed_ms, 3),
                        "query_count": len(captured),
                        "recorded_db_ms": round(db_ms, 3),
                        "response_bytes": len(response.content),
                    }
                )

    summary = []
    for path in ENDPOINTS:
        rows = [row for row in results if row["path"] == path]
        summary.append(
            {
                "path": path,
                "samples": len(rows),
                "mean_elapsed_ms": round(sum(row["elapsed_ms"] for row in rows) / len(rows), 3),
                "query_count_min": min(row["query_count"] for row in rows),
                "query_count_max": max(row["query_count"] for row in rows),
                "mean_recorded_db_ms": round(sum(row["recorded_db_ms"] for row in rows) / len(rows), 3),
                "response_bytes": rows[0]["response_bytes"],
            }
        )

    output = ROOT / "artifacts/load-test/query-profile" / label
    output.mkdir(parents=True, exist_ok=False)
    payload = {
        "label": label,
        "database": "heyzzabi_test",
        "counts": counts,
        "method": "Django APIClient + CaptureQueriesContext; 1 warmup excluded, 5 measured calls",
        "limitations": [
            "Django internal request path; excludes HTTPS, Gunicorn, Vercel and nginx",
            "MySQL-reported query time is low-resolution and excludes Python serialization",
            "Login is excluded; PM test account used",
        ],
        "summary": summary,
        "requests": results,
    }
    (output / "profile.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
