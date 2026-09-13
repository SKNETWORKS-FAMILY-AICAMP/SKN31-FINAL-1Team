"""
run_pipeline.py

실제 LLM을 호출해서 회의록 → 구조화 JSON → 기획서까지 전체 파이프라인을
DB 없이 눈으로 확인하는 스크립트. 모델별 결과 비교용.

사용법:
    python run_pipeline.py                          # sample_meeting.txt 사용
    python run_pipeline.py path/to/회의록.txt        # 다른 회의록 파일 지정
    OPENAI_MODEL=gpt-5.6-luna python run_pipeline.py # 모델 바꿔 실행

결과는 out/plan_document_output.json 에 저장된다(DB에는 아무것도 안 쓴다).
DB의 실제 회의록으로 돌리려면 test_db_meeting_to_plan.py 를 쓴다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# .env 는 프로젝트 루트(ai/의 상위)에 있다.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from meeting_analysis_x.node import run as analyze_meeting
from plan_draft.agent import run as generate_plan
from shared.retry_config import describe

AI_DIR = Path(__file__).resolve().parent
DEFAULT_TRANSCRIPT = AI_DIR / "sample_meeting.txt"


def main() -> None:
    transcript_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRANSCRIPT
    transcript = transcript_path.read_text(encoding="utf-8")

    print(describe())
    print(f"\n회의록: {transcript_path.name} ({len(transcript)}자)")

    print("\n" + "=" * 70)
    print("1단계: 회의록 → 구조화 JSON (LLM 호출)")
    print("=" * 70)
    t0 = time.time()
    result = analyze_meeting(transcript, "MTG-DEMO")
    structured = result.data
    print(f"완료 ({time.time() - t0:.1f}초)")
    if result.notes:
        print("notes:", result.notes)
    unresolved = structured.get("unresolved") or []
    if unresolved:
        print(f"unresolved {len(unresolved)}건:", unresolved)
    print("\n[구조화 JSON 일부]")
    print(json.dumps(structured, ensure_ascii=False, indent=2)[:2000])
    print("...(생략)...")

    print("\n" + "=" * 70)
    print("2단계: 구조화 JSON → 기획서 (LLM 호출)")
    print("=" * 70)
    t1 = time.time()
    doc = generate_plan(structured, proposal_id="TEST-DEMO")
    plan = doc.model_dump(mode="json")
    print(f"완료 ({time.time() - t1:.1f}초) · 총 {time.time() - t0:.1f}초")

    sections = plan.get("sections", [])
    print(f"\n[섹션 {len(sections)}개]")
    for s in sections:
        flag = "⚠️ 비어있음" if s.get("is_incomplete") else "OK"
        body = (s.get("content_html") or "").replace("\n", " ")[:80]
        print(f"  [{s.get('key', '?'):14}] {s.get('title', '?'):16} {flag:10} {body}")

    out_dir = AI_DIR / "out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "plan_document_output.json"
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n전체 결과 저장: {out_path}")


if __name__ == "__main__":
    main()
