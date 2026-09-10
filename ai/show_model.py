"""
show_model.py — 지금 AI 에이전트가 어떤 모델·설정으로 도는지 확인한다.

    cd ai
    ../.venv/bin/python show_model.py          # .env 기준 설정만 출력
    ../.venv/bin/python show_model.py --ping   # 실제 OpenAI API로 키·모델명 유효성까지 확인

--ping은 completion을 만들지 않고 Models API(models.retrieve)만 호출하므로
토큰 비용이 거의 없다. 모델명 오타(404)·잘못된 키(401)를 파이프라인을
끝까지 돌리기 전에 걸러준다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

# .env는 프로젝트 루트(ai/의 상위)에 있다.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from shared.retry_config import DEFAULT_MODEL, describe


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--ping",
        action="store_true",
        help="실제 OpenAI API를 호출해 현재 키로 이 모델을 쓸 수 있는지 확인",
    )
    args = ap.parse_args()

    print(describe())

    if not args.ping:
        return

    from shared.llm_client import get_raw_client

    print("\nAPI 확인 중...", flush=True)
    try:
        info = get_raw_client().models.retrieve(DEFAULT_MODEL)
    except Exception as e:  # noqa: BLE001 — 사용자에게 원인만 보여주면 됨
        print(f"✗ 실패 — {type(e).__name__}: {e}")
        raise SystemExit(1)
    print(f"✓ OK — '{DEFAULT_MODEL}' 사용 가능 (owned_by={getattr(info, 'owned_by', '?')})")


if __name__ == "__main__":
    main()
