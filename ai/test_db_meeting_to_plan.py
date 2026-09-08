"""
DB의 더미 회의록으로 노드 ①②(analyze_meeting → generate_plan)를 실행해서
기획서가 어떤 식으로 생성되는지 확인하는 테스트 스크립트.

- Django를 띄우지 않고 .env의 MYSQL_DB/MYSQL_USER/MYSQL_PASSWORD/MYSQL_HOST/MYSQL_PORT로 직접 DB에 연결합니다.
- DB에는 아무것도 저장하지 않습니다. 결과는 화면 출력 + 로컬 JSON 파일로만 남깁니다.

사용법:
    python test_db_meeting_to_plan.py 3           # meeting_id(정수 PK)로 지정
    python test_db_meeting_to_plan.py             # 생략 시 가장 최근 회의록 사용

주의: DB 명세서에는 meeting_no(VARCHAR, "MTG-001" 형식) 컬럼이 있었지만
실제 DB에는 없고, meeting_id(int, auto_increment)만 존재합니다.

필요 패키지 (ai/ 기존 패키지에 추가로 필요):
    pip install sqlalchemy pymysql --break-system-packages
    (DB가 PostgreSQL이면 pymysql 대신: pip install psycopg2-binary)
"""

import sys
import json
import time
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()  # 레포 루트 또는 ai/.env

# ai/ 를 import 경로에 추가 (레포 구조에 맞게 조정)
AI_DIR = Path(__file__).resolve().parent  # 이 스크립트를 ai/ 폴더 안에 두는 걸 가정
sys.path.insert(0, str(AI_DIR))

from meeting_analysis.node import run as analyze_meeting
from plan_draft.agent import run as generate_plan

from sqlalchemy import create_engine, text


def build_db_url() -> str:
    db = os.getenv("MYSQL_DB")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    host = os.getenv("MYSQL_HOST")
    port = os.getenv("MYSQL_PORT")

    missing = [k for k, v in {
        "MYSQL_DB": db, "MYSQL_USER": user, "MYSQL_PASSWORD": password,
        "MYSQL_HOST": host, "MYSQL_PORT": port,
    }.items() if not v]
    if missing:
        raise RuntimeError(f".env에 다음 값이 비어 있습니다: {missing}")

    from urllib.parse import quote_plus
    return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"


def get_meeting_row(meeting_id: str | None):
    # 실제 DB 컬럼명: meeting_id(PK, int) / meeting_no 없음 / participant -> attendees
    db_url = build_db_url()
    engine = create_engine(db_url)
    with engine.connect() as conn:
        if meeting_id:
            row = conn.execute(
                text("SELECT meeting_id, title, content FROM meeting_note WHERE meeting_id = :mid"),
                {"mid": meeting_id},
            ).mappings().first()
        else:
            row = conn.execute(
                text("SELECT meeting_id, title, content FROM meeting_note ORDER BY created_at DESC LIMIT 1")
            ).mappings().first()

    if row is None:
        raise RuntimeError(f"회의록을 찾지 못했습니다 (meeting_id={meeting_id}). DB에 더미 데이터가 들어갔는지 확인해주세요.")

    return row


def summarize_section(section: dict) -> str:
    key = section.get("key")
    title = section.get("title")
    incomplete = section.get("is_incomplete")
    body = section.get("content_html") or ""
    preview = (body[:80] + "...") if len(body) > 80 else body
    flag = "⚠️ 비어있음" if incomplete else "OK"
    return f"  [{key:12}] {title:14} {flag:10} {preview}"


def main():
    meeting_id = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"1) DB에서 회의록 조회 중... (meeting_id={meeting_id or '최신 1건'})")
    row = get_meeting_row(meeting_id)
    print(f"   -> meeting_id={row['meeting_id']}  title={row['title']}")
    print(f"   -> content 길이: {len(row['content'] or '')}자")

    if not row["content"]:
        print("   ⚠️ content가 비어 있습니다. 이 회의록으로는 테스트해도 의미가 없습니다.")
        return

    print("\n2) 노드 ① 회의록 구조화 실행 중...")
    t0 = time.time()
    result = analyze_meeting(row["content"], str(row["meeting_id"]))
    structured = result.data
    t1 = time.time()
    print(f"   -> 완료 ({t1 - t0:.1f}초)")
    unresolved_1 = structured.get("unresolved") or []
    if unresolved_1:
        print(f"   -> unresolved {len(unresolved_1)}건: {unresolved_1}")

    print("\n3) 노드 ② 기획서 생성 실행 중...")
    doc = generate_plan(structured, proposal_id=f"TEST-{row['meeting_id']}")
    plan = doc.model_dump(mode="json")
    t2 = time.time()
    print(f"   -> 완료 ({t2 - t1:.1f}초)")
    print(f"   -> 총 소요시간 (①+②): {t2 - t0:.1f}초")

    sections = plan.get("sections", [])
    print(f"\n4) 결과 — 섹션 {len(sections)}개 (7개여야 정상)")
    for s in sections:
        print(summarize_section(s))

    unresolved_2 = plan.get("unresolved") or []
    if unresolved_2:
        print(f"\n   기획서 unresolved: {unresolved_2}")

    # 4번(features) 섹션 상세 출력
    features_section = next((s for s in sections if s.get("key") == "features"), None)
    if features_section and features_section.get("features"):
        print("\n5) 주요 기능(features) 상세:")
        for f in features_section["features"]:
            print(f"   - [{f.get('priority')}] {f.get('title')}: {f.get('description') or '(설명 없음)'}")

    # 전체 결과를 로컬 파일로 저장 (DB에는 저장하지 않음)
    out_dir = AI_DIR / "out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"test_{row['meeting_id']}.json"
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n전체 결과 저장: {out_path}")


if __name__ == "__main__":
    main()
