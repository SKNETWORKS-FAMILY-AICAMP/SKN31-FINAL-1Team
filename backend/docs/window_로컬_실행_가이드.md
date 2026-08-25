### 백엔드 — Windows (PowerShell)

1) 터미널에서 다음 명령어 순차적으로 실행
```powershell
cd server
uv venv .venv --python=3.13
.venv\Scripts\activate
uv pip install -r requirements.txt
copy .env.example .env

python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
2) env 파일 생성후 값 채우기
```
SECRET_KEY=change-me-to-a-long-random-string
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
