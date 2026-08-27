# Django SQLite to AWS RDS 데이터 이관 가이드 (Data Migration Guide)

이 문서는 개발 환경의 `db.sqlite3` 데이터를 데이터 손실 없이 **AWS RDS (PostgreSQL / MySQL)**로 이전하기 위한 표준 절차를 안내합니다.

---

## 📌 개요 및 주의사항

* **목적:** 로컬/개발 환경(`db.sqlite3`)의 데이터를 운영/개발용 AWS RDS DB로 안전하게 이관.
* **주요 방식:** Django 내장 직렬화 도구 (`dumpdata` / `loaddata`) 사용.
* **⚠️ 주의사항:**
  * 이관 작업 시작 전, `db.sqlite3` 파일의 복사본(백업)을 별도로 보관하세요.
  * 데이터 유실 방지를 위해 이관 작업 중에는 앱 서버 작동을 일시 중지하는 것을 권장합니다.

---

## 🚀 상세 이관 절차 (4 단계)

### STEP 1: SQLite 데이터 백업 (`dumpdata`)

Django의 ContentType 및 Auth Permission 모델은 새 DB에 `migrate` 실행 시 자동으로 생성되므로, 백업 데이터에서 제외해야 PK 충돌 및 중복 에러를 방지할 수 있습니다.

터미널에서 아래 명령어를 실행하여 데이터를 JSON 형태로 추출합니다:

```bash
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission --indent 4 > datadump.json
```

* `-e contenttypes`: ContentType 모델 데이터 제외
* `-e auth.Permission`: Permission 모델 데이터 제외
* `--natural-foreign`, `--natural-primary`: 외래키/기본키 참조 관계 오류 방지
* `--indent 4`: 가독성을 위한 인덴트 적용

---

### STEP 2: RDS 연결 설정 (`settings.py`)

1. **DB 드라이버 설치**
   * **PostgreSQL 사용 시:**
     ```bash
     pip install psycopg2-binary
     ```
   * **MySQL 사용 시:**
     ```bash
     pip install mysqlclient
     ```

2. **`settings.py` 변경**
   `DATABASES` 설정을 AWS RDS 데이터베이스 접속 정보로 변경합니다.

   ```python
   # settings.py

   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',  # PostgreSQL: django.db.backends.postgresql / MySQL: django.db.backends.mysql
           'NAME': 'your_rds_db_name',                 # RDS 데이터베이스 이름
           'USER': 'your_rds_username',                # RDS Master Username
           'PASSWORD': 'your_rds_password',            # RDS Master Password
           'HOST': 'your-rds-endpoint.xxx.amazonaws.com', # RDS 엔드포인트
           'PORT': '5432',                             # PostgreSQL: 5432 / MySQL: 3306
       }
   }
   ```

---

### STEP 3: RDS 스키마(테이블) 생성 (`migrate`)

새로 연결된 AWS RDS 데이터베이스에 데이터가 들어갈 빈 테이블 구조를 생성합니다.

```bash
python manage.py migrate
```

---

### STEP 4: RDS로 데이터 복원 (`loaddata`)

STEP 1에서 추출한 `datadump.json` 파일의 데이터를 RDS에 복원합니다.

```bash
python manage.py loaddata datadump.json
```

복원이 성공적으로 완료되면 "Installed X object(s) from 1 fixture(s)" 메시지가 표시됩니다.

---

## 🛠️ 이관 후 후속 조치 및 트러블슈팅

### 1. PostgreSQL Sequence 초기화 (PostgreSQL 필수)
PostgreSQL로 이전한 후, 테이블의 Auto-Increment Sequence가 이전 데이터의 마지막 PK 값을 인식하지 못해 새 데이터를 `create` 할 때 `IntegrityError (duplicate key value violates unique constraint)`가 발생할 수 있습니다.

**해결 방법:**
아래 명령어로 스퀀시 재설정 SQL을 생성 및 적용합니다.

```bash
python manage.py sqlsequencereset <app_name>
```
*출력된 SQL 구문을 `python manage.py dbshell`에 접속하여 실행하거나, 각 앱별로 확인 및 동기화합니다.*

### 2. 인코딩 에러 (UTF-8)
Windows 환경에서 `datadump.json` 생성 시 기본 인코딩 문제로 한글이 깨질 수 있습니다. `datadump.json` 파일 저장 시 반드시 **UTF-8** 형식으로 저장되었는지 확인하세요.

---
*문서 작성일: 2026년*
