# WSL 작업환경 설정

## 1. 우분투 설치
1. 터미널을 관리자 권한으로 실행
`wsl --install`
2. 버전확인 `wsl -l -v`

## 2. 우분투 실행
터미널을 관리자권한으로 실행 ->
1. 우분투 접속 `wsl -d Ubuntu`
2. 파이썬 가상환경 생성 도구 설치  
`sudo apt update`  
`sudo apt install -y python3-venv python3-pip`
3. 프로젝트 생성  
`mkdir ~/my-project`: my-project에 생성하고자하는 프로젝트명 넣으면 됨  
3-1. 생성한 폴더로 이동  
`cd ~/my-project`

4. 깃 클론  
`git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN31-FINAL-1Team.git`  
`code .`  
5. vscode 열리면 확장프로그램 python 설치  
5-1. uv 패키지 매니저 설치  
`curl -Ls https://astral.sh/uv/install.sh | bash`  
`source ~/.bashrc`  
5-2. 가상환경 설치 및 활성화  
`uv venv`  
`source .venv/bin/activate`  
5-3. 깃폴더로 이동 `cd SKN31-FINAL-1Team`  
5-4. 내 브랜치폴더로 이동 `git switch <브랜치명>`  
5-5. 브랜치 이동 확인 `git branch`

## 3. 작업시작전 필수 진행
1. develop 최신 상태로 맞추기  
`git checkout develop`  
`git pull origin develop`  
2. 오늘 할 작업 브랜치 만들기 (WBS 번호 사용)  
`git checkout -b <브랜치명>` : 예시) `git checkout -b feat/6-2-auth-api`  
3. 수시로 커밋 진행  
`git add .`  
`git commit -m "메세지"` : 예시) `git commit -m "feat: JWT 토큰 발급 로직 구현"`  
4. 푸시 진행  
`git push origin <브랜치명>` : 예시) `git push origin feat/6-2-auth-api`

## 4. 브랜치 병합(PM)
1. 메인 브랜치로 이동
`git switch main`

2. 최신 코드 불러오기(PM)
`git pull origin main`

3. 작업한 브랜치 병합 : 코드리뷰 후 진행
`git merge <브랜치명>`

## 5. 브랜치 병합 후 할일
1. 삭제할 브랜치가 메인 브랜치(예: main)로 이동
`git switch main`

2. 로컬 브랜치 삭제 (병합이 완료된 경우)
`git branch -d <브랜치명>`

3. (필요시) 병합하지 않은 브랜치를 강제로 삭제할 때
`git branch -D <브랜치명>`

4. 원격 브랜치 삭제
`git push origin --delete <브랜치명>`

---
---

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
3) DB 저장 `python manage.py migrate`
3-1) 테스트 계정 주입 `python manage.py loaddata seed_users.json`
4) 서버 실행하기 `python manage.py runserver`
5) 테스트 서버 실행하기(웹에서 아래 주소 접속)
`http://127.0.0.1:8000/api/v1/swagger/`