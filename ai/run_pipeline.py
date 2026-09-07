"""
run_pipeline.py

실제 LLM을 호출해서 회의록 -> 구조화 JSON -> 기획서 12항목까지
전체 파이프라인을 눈으로 확인하기 위한 스크립트.

사용법:
    python run_pipeline.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# .env 가 ai/ 의 상위 폴더(프로젝트 루트)에 있으므로 경로를 명시한다.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from meeting_analysis.agent import analyze_meeting
from meeting_analysis.schemas import Meeting
from plan_draft.agent import generate_plan_document

TRANSCRIPT_PATH = "sample_meeting.txt"


def main() -> None:
    with open(TRANSCRIPT_PATH, encoding="utf-8") as f:
        transcript = f.read()

    meeting = Meeting(
        id="MTG-2026-08-25-DEMO",
        title="AI 회의 분석 서비스 1차 기능 정의 회의",
        participants=["정하늘", "오세진", "문가영"],
        created_at=datetime(2026, 8, 25, 15, 0),
    )

    print("=" * 70)
    print("1단계: 회의록 -> 구조화 JSON (LLM 호출)")
    print("=" * 70)

    plan, report = analyze_meeting(
        transcript=transcript,
        meeting=meeting,
        purpose="AI 회의 분석 서비스의 1차 개발 기능과 제외 범위를 결정한다.",
        project_id="PJT-DEMO",
    )

    print("\n[후처리 리포트]")
    print(report.summary())

    print("\n[구조화 JSON 일부]")
    print(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)[:2000])
    print("...(생략)...")

    print("\n" + "=" * 70)
    print("2단계: 구조화 JSON -> 기획서 12항목 (LLM 미사용, 규칙 기반)")
    print("=" * 70)

    doc = generate_plan_document(plan)

    print(f"\n제목: {doc.head.title}")
    print(f"출처 회의: {doc.head.meeting_title} ({doc.head.date})")
    print(f"참석자: {', '.join(doc.head.participants)}")

    print("\n[목차]")
    for entry in doc.toc:
        status = "비어있음" if entry.is_empty else "내용 있음"
        print(f"  {entry.no}. {entry.title} - {status}")

    print("\n[전체 섹션 상세]")
    for section in doc.sections:
        print(f"\n--- {section.no}. {section.title} ---")
        if section.is_empty:
            print(f"  ({section.empty_message})")
            continue
        for block in section.blocks:
            if block.kind == "field":
                print(f"  [{block.label}] {block.text}")
            elif block.kind == "list":
                if block.heading:
                    print(f"  <{block.heading}>")
                for item in block.items:
                    prefix = f"{item.prefix}: " if item.prefix else ""
                    print(f"    - {prefix}{item.text}")
            elif block.kind == "table":
                print(f"  컬럼: {block.columns}")
                for row, badge in zip(block.rows, block.badges or [""] * len(block.rows)):
                    badge_str = f" [{badge}]" if badge else ""
                    print(f"    {row}{badge_str}")
            elif block.kind == "flow":
                print(f"  <{block.heading}>")
                print(f"    단계: {' -> '.join(block.steps)}")
                print(f"    결과: {block.result}")
            elif block.kind == "note":
                print(f"  * {block.text}")

    # 최종 결과 파일로 저장
    with open("plan_document_output.json", "w", encoding="utf-8") as f:
        json.dump(doc.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    print("\n\n전체 결과가 plan_document_output.json 에 저장되었습니다.")


if __name__ == "__main__":
    main()