### 백엔드 — Windows (PowerShell)

1) 터미널에서 다음 명령어 순차적으로 실행
```powershell
cd server
uv venv .venv --python=3.13
.venv\Scripts\activate
uv pip install -r requirements.txt
copy .env.example .env
```
2) env 파일 생성후 아래 내용 복사
```
# 필수
SECRET_KEY=change-me-to-a-long-random-string
DEBUG=True

# 배포 시 채웁니다 (콤마 구분)
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'http://localhost:8000',
    'http://127.0.0.1:8000'
]

# DATABASE_URL=postgres://eden:PASSWORD@eden-db.xxxx.ap-northeast-2.rds.amazonaws.com:5432/eden
DATABASE_URL=sqlite:///db.sqlite3

# LLM
OPENAI_API_KEY=<<본인 API key 입력>>
```
3) DB 저장 `python manage.py migrate`
4) Docker desktop 실행 후 redis 서버 세팅
```
docker run -d --name redis-server -p 6379:6379 redis:alpine
```
5) celery worker 실행
```
celery -A config worker -l info -P solo
```
6) 새 터미널에서 서버 접속
```
python manage.py runserver 8080
```

### 프론트엔드 — Windows (PowerShell)
1) .env.local 파일 생성하고 url 추가
```
VITE_API_BASE_URL=http://127.0.0.1:8080
```
2) 새 터미널 추가한 후 다음 명령어 실행
```powershell
cd frontend
npm install
npm run dev
http://localhost:5173/ 접속
```
