# 로컬환경 실행방법
## 백엔드 — Windows (PowerShell)

1) 터미널에서 다음 명령어 순차적으로 실행
```powershell
cd backend
uv venv .venv --python=3.13
.venv\Scripts\activate
uv pip install -r requirements.txt
copy .env.example .env
```
1-1) 아래 코드 실행하여 django secret key 생성한 후 복사하여 env에 붙여넣기
```
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
2) env 파일 내 key 값 채우기
```
SECRET_KEY=<<본인 django API key 입력>>
OPENAI_API_KEY=<<본인 API key 입력>>
```
3) DB 저장  
`python manage.py migrate`  
4) 서버 실행하기   
`python manage.py runserver`
5) API swagger 서버 실행하기(웹에서 아래 주소 접속되는지 확인)
`http://127.0.0.1:8000/api/docs/swagger/`