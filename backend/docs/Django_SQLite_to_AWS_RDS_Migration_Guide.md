# Django SQLite to AWS RDS 데이터 이관 가이드 (Data Migration Guide)

이 문서는 개발 환경의 `db.sqlite3` 데이터를 데이터 손실 없이 **AWS RDS (PostgreSQL / MySQL)**로 이전하기 위한 표준 절차를 안내합니다.

* **작성일 : 2026-08-27**
* **작성자 : 김가율**
---

## 📌 개요 및 주의사항

* **목적:** 로컬/개발 환경(`db.sqlite3`)의 데이터를 운영/개발용 AWS RDS DB로 안전하게 이관.
* **주요 방식:** Django 내장 직렬화 도구 (`dumpdata` / `loaddata`) 사용.
* **⚠️ 주의사항:**
  * 이관 작업 시작 전, `db.sqlite3` 파일의 복사본(백업)을 별도로 보관하세요.
  * 데이터 유실 방지를 위해 이관 작업 중에는 앱 서버 작동을 일시 중지하는 것을 권장합니다.

---

## 🚀 상세 이관 절차 (4 단계)
### * [window_로컬_실행_가이드.md]를 참고하여 로컬 백엔드 설정부터 합니다!
### * 작업은 backend 폴더 터미널에서 진행합니다!

### STEP 1: SQLite 데이터 백업 (`dumpdata`)

Django의 ContentType 및 Auth Permission 모델은 새 DB에 `migrate` 실행 시 자동으로 생성되므로, 백업 데이터에서 제외해야 PK 충돌 및 중복 에러를 방지할 수 있습니다.

터미널에서 아래 명령어를 실행하여 데이터를 JSON 형태로 추출합니다:

```
* backend 폴더로 이동 한 후 진행합니다.

# 1. 패키지 목록 업데이트
`sudo apt update`

# 2. 필수 빌드 도구 및 MySQL 개발 라이브러리 설치
`sudo apt install -y pkg-config default-libmysqlclient-dev build-essential python3-dev`

#3. db.sqlite3 데이터를 더미데이터로 백업
`python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission --indent 4 > datadump.json`
```

* `-e contenttypes`: ContentType 모델 데이터 제외
* `-e auth.Permission`: Permission 모델 데이터 제외
* `--natural-foreign`, `--natural-primary`: 외래키/기본키 참조 관계 오류 방지
* `--indent 4`: 가독성을 위한 인덴트 적용

---

### STEP 2: RDS 연결 설정

1. **DB 드라이버 설치**
   * **PostgreSQL 사용 시:**
     ```bash
     uv pip install psycopg2-binary
     ```
   * **MySQL 사용 시:**
     ```bash
     uv pip install mysqlclient
     ```

2. **`.env` 변경**
   
   AWS RDS 데이터베이스 접속 정보를 채웁니다.

   ```python
    MYSQL_DB=MYSQL_DB
    MYSQL_USER=MYSQL_USER
    MYSQL_PASSWORD=MYSQL_PASSWORD
    MYSQL_HOST=MYSQL_HOST
    MYSQL_PORT=3306
   ```

---

### STEP 3: RDS 스키마(테이블) 생성 (`migrate`)

새로 연결된 AWS RDS 데이터베이스에 데이터가 들어갈 빈 테이블 구조를 생성합니다.

```bash
* backend 폴더 터미널에서 진행합니다!

`python manage.py migrate`
```

---

### STEP 4: RDS로 데이터 복원 (`loaddata`)

STEP 1에서 추출한 `datadump.json` 파일의 데이터를 RDS에 복원합니다.

```bash
* backend 폴더 터미널에서 진행합니다!

`python manage.py loaddata datadump.json`
```

복원이 성공적으로 완료되면 "Installed X object(s) from 1 fixture(s)" 메시지가 표시됩니다.

---