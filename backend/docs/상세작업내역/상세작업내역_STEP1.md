# 단계별 상세 작업 내역 (Detailed Tasks)

### STEP 1: 초기 프로젝트 세팅 & 아키텍처 설정
* **작업일 : 2026-08-24**
* **개발 환경 세팅**
  * Python 가상환경(`venv`) 구성 및 라이브러리 설치
    ```bash
    # 터미널을 관리자 권한으로 실행
    1) wsl 설치 : wsl --install
    2) wsl 버전 확인 : wsl -l -v
    3) 우분투 접속 : wsl -d Ubuntu
    4) 파이썬 가상환경 생성 도구 설치 :
        sudo apt update
        sudo apt install -y python3-venv python3-pip
    5) 프로젝트 생성(my-project) :
        mkdir ~/my-project
    6) 생성한 프로젝트로 이동 :
        cd ~/my-project
    7) git clone :
        git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN31-FINAL-1Team.git
        code .
    8) vscode 열리면 확장프로그램 python 설치
    9) uv 패키지 매니저 설치 :
        curl -Ls https://astral.sh/uv/install.sh | bash
        source ~/.bashrc
    10) 가상환경 설치 및 활성화 :
        uv venv
        source .venv/bin/activate
    11) 필수라이브러리 설치 :
        uv pip install -r requirements.txt
    ```

  * `django-admin startproject` 실행 및 App 단위 분리 (`users`, `common`, `meetings`, `specs`, `tasks`)

    ```bash
    # 터미널에서 아래 코드를 순차적으로 실행
    1) django-admin startproject config .
    2) python manage.py startapp users
    3) python manage.py startapp common
    4) python manage.py startapp meetings
    5) python manage.py startapp specs
    6) python manage.py startapp tasks
    ```
  * 앱을 만든 후에는 Django가 이 앱들을 인식할 수 있도록 config/settings.py 파일의 INSTALLED_APPS 목록에 등록
    ```python
    # Third Party 패키지
    'rest_framework',
    'corsheaders',
    'drf_spectacular',

    # Local Apps (직접 만든 앱들)
    'users',
    'common',
    'meetings',
    'specs',
    'tasks',
    ```
  * 언어와 기준시 설정 : config/settings.py 파일
    ```python
    LANGUAGE_CODE = 'ko-kr'     # 언어코드 설정
    TIME_ZONE = 'Asia/Seoul'    # 시간 기준 나라 설정
    ```

  * 산출물: `requirements.txt`, 패키지별 역할 설명서, 프로젝트 디렉토리 구조 설명서

* **DB(데이터베이스) 설정 및 모델링 작업**

  * **DB & 환경변수 설정**
    * 환경변수(.env) 파일 생성 및 설정
    * Django 기본 DB인 SQLite 대신 PostgreSQL/MySQL 등 실제 사용할 DB를 연결하고, 보안 정보(.env)를 격리합니다.
    * config/settings.py에 .env 연동 코드 적용
    ```python
    import os
    import environ
    from pathlib import Path

    BASE_DIR = Path(__file__).resolve().parent.parent

    # --- env 설정 추가 ---
    env = environ.Env(
        DEBUG=(bool, False)
    )
    environ.Env.read_env(os.path.join(BASE_DIR, '.env'))
    # ----------------------

    # 기존 코드 수정: 하드코딩된 값 대신 env에서 가져오도록 변경
    SECRET_KEY = env('SECRET_KEY')
    DEBUG = env('DEBUG', default=True)

    ALLOWED_HOSTS = []

    # 기존 DATABASES 구문을 교체합니다.
    DATABASES = {
        'default': env.db('DATABASE_URL')
    }
    ```
  * 산출물: `config/settings.py`, `.env.example`

---

* **작업일 : 2026-08-24**
* **CORS & Security 설정**
  * `django-cors-headers` 설정으로 React 개발/운영 도메인 허용
  * CSRF 및 Security Middleware 점검

    1) django-cors-headers 라이브러리를 활용
      -> config/settings.py 파일 내부의 INSTALLED_APPS에 `'corsheaders',` 앱 추가되어있는지 확인. 없으면 추가하기.

    2) MIDDLEWARE에 미들웨어 추가
      -> `'corsheaders.middleware.CorsMiddleware',`

    3) CORS 허용 도메인 설정
      - 개발 환경에서 프론트엔드가 접근할 수 있도록 허용 목록을 정의
      -> config/settings.py 파일 하단에 코드 추가
    ```python
    # React, Vite 등 프론트엔드 개발 서버 주소 허용
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",   # React (Create React App, Next.js 등)
        "http://127.0.0.1:3000",
        "http://localhost:5173",   # Vite (React / Vue 등)
        "http://127.0.0.1:5173",
        "http://localhost:8080",   # Vue CLI 등
    ]

    # 인증 정보(Cookie, Authorization 헤더 등)를 포함한 요청 허용
    CORS_ALLOW_CREDENTIALS = True

    CORS_ALLOW_HEADERS = [
        'accept',
        'accept-encoding',
        'authorization',
        'content-type',
        'dnt',
        'origin',
        'user-agent',
        'x-csrftoken',
        'x-requested-with',
    ]
    ```

---