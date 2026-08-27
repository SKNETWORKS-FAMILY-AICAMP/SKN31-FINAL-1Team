"""
shared/django_bootstrap.py

ai/ 패키지(별도 서비스)가 backend/의 Django 모델(ORM)을 직접 import해서 쓰기 위한
초기화 모듈. Plan 등 backend 모델을 쓰는 코드는 그 모델을 import하기 전에
반드시 이 모듈을 먼저 import해야 한다 (django.setup() 부작용을 위해).

  import shared.django_bootstrap  # noqa: F401  (반드시 다른 backend 모델 import보다 먼저)
  from plans.models import Plan

주의 — 이 방식은 ai/ 실행 환경과 backend/ 설정(.env, DATABASES, 설치 앱)이
동일 파이썬 프로세스에서 로드된다는 뜻이다. 즉:
  - ai/ 쪽 requirements에 Django + DB 드라이버(mysqlclient 또는 pymysql)가 추가로 필요하다.
  - backend/.env(SECRET_KEY, DATABASE_URL 등)를 ai/ 프로세스도 읽을 수 있어야 한다.
  - 이 결합이 부담스럽다면 대안은 REST API(DRF) 경유 호출이다 — 팀 논의 후 정할 것.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
