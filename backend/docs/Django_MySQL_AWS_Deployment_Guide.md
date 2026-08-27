# Django REST Framework & MySQL - AWS Infrastructure & Deployment Guide

 본 가이드는 **Django Models**와 **MySQL DB** 간의 동기화 검증부터 시작하여, **AWS RDS(MySQL)** 및 **EC2(Ubuntu)** 인프라 구축, **Nginx + Gunicorn** 기반 프로덕션 배포 및 **Certbot SSL(HTTPS)** 적용까지 전체 배포 파이프라인의 전 과정을 단계별로 상세히 다룹니다.

---

## 📋 목차
1. [전체 프로세스 흐름도](#1-전체-프로세스-흐름도)
2. [1단계: 로컬/WSL 환경에서 Django ↔ MySQL 동기화 검증](#2-1단계-로컬wsl-환경에서-django--mysql-동기화-검증)
3. [2단계: AWS RDS (MySQL 데이터베이스) 구축](#3-2단계-aws-rds-mysql-데이터베이스-구축)
4. [3단계: AWS EC2 인프라 구축 및 보안 그룹 설정](#4-3단계-aws-ec2-인프라-구축-및-보안-그룹-설정)
5. [4단계: EC2 서버 환경 세팅 및 프로젝트 배포](#5-4단계-ec2-서버-환경-세팅-및-프로젝트-배포)
6. [5단계: Django ↔ AWS RDS 마이그레이션 실행](#6-5단계-django--aws-rds-마이그레이션-실행)
7. [6단계: Nginx + Gunicorn 연동 (Web Server & WSGI)](#7-6단계-nginx--gunicorn-연동-web-server--wsgi)
8. [7단계: Celery & Redis 비동기 워커 Background 서비스 등록](#8-7단계-celery--redis-비동기-워커-background-서비스-등록)
9. [8단계: 도메인 연결 및 SSL(HTTPS) 적용](#9-8단계-도메인-연결-및-sslhttps-적용)
10. [트러블슈팅 & 체크리스트](#10-트러블슈팅--체크리스트)

---

## 1. 전체 프로세스 흐름도

```text
[1. Local/WSL Django & MySQL Sync Test]
                    │
                    ▼
[2. AWS RDS (MySQL) Provisioning & Security Group]
                    │
                    ▼
[3. AWS EC2 (Ubuntu 22.04) Instance & Elastic IP]
                    │
                    ▼
[4. Project Clone & Virtualenv & MySQL Client Driver]
                    │
                    ▼
[5. Run `python manage.py migrate` towards RDS]
                    │
                    ▼
[6. Gunicorn (WSGI) + Nginx (Reverse Proxy) Configuration]
                    │
                    ▼
[7. Celery Worker & Redis Daemonization]
                    │
                    ▼
[8. Route53 Domain & Certbot SSL (HTTPS) Finalization]
```

---

## 2. 1단계: 로컬/WSL 환경에서 Django ↔ MySQL 동기화 검증

AWS로 배포하기 전, 로컬/WSL 환경의 MySQL에 Django 모델을 정상적으로 마이그레이션하여 스키마 일치 여부를 검증합니다.

### 2.1 필수 패키지 설치 (WSL / Linux)
MySQL 드라이버 컴파일에 필요한 시스템 라이브러리와 Python MySQL 드라이버를 설치합니다.

```bash
# Ubuntu/WSL 패키지 업데이트 및 C 컴파일러, MySQL 개발 헤더 설치
sudo apt update && sudo apt install -y python3-dev default-libmysqlclient-dev build-essential pkg-config

# 가상환경 진입 후 mysqlclient 설치
source venv/bin/activate
pip install mysqlclient PyMySQL
```

### 2.2 로컬 MySQL 데이터베이스 및 유저 생성
```sql
-- MySQL 접속 (Terminal)
mysql -u root -p

-- 데이터베이스 생성 (UTF-8 MB4 설정)
CREATE DATABASE dev_pipeline_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 사용자 생성 및 권한 부여
CREATE USER 'dev_user'@'localhost' IDENTIFIED BY 'your_password_here';
GRANT ALL PRIVILEGES ON dev_pipeline_db.* TO 'dev_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 2.3 Django `settings.py` DB 설정 수정
```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'dev_pipeline_db',
        'USER': 'dev_user',
        'PASSWORD': 'your_password_here',
        'HOST': '127.0.0.1',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}
```

### 2.4 마이그레이션 실행 및 스키마 검증
```bash
# 1. 마이그레이션 파일 생성
python manage.py makemigrations

# 2. DB에 테이블 반영
python manage.py migrate

# 3. 마이그레이션 상태 확인 (모든 항목에 [X] 표시되어야 함)
python manage.py showmigrations

# 4. Superuser 생성 테스트
python manage.py createsuperuser
```

---

## 3. 2단계: AWS RDS (MySQL 데이터베이스) 구축

### 3.1 RDS 인스턴스 생성 절차
1. **AWS Console** ➔ **RDS** ➔ **데이터베이스 생성** 클릭
2. **데이터베이스 생성 방식**: 표준 생성 (Standard Create)
3. **엔진 옵션**: `MySQL` (버전: 8.0.x 권장)
4. **템플릿**: 프리티어 (Free Tier) 또는 개발/테스트
5. **설정**:
   * **DB 인스턴스 식별자**: `pipeline-rds-mysql`
   * **마스터 사용자 이름**: `admin`
   * **마스터 암호**: `안전한_비밀번호_입력`
6. **인스턴스 구성**: `db.t3.micro` 또는 `db.t4g.micro`
7. **스토리지**: 스토리지 자동 조정 활성화 (기본값 20GiB)
8. **연결 (Connectivity)**:
   * **VPC**: Default VPC 선택
   * **퍼블릭 액세스**: `아니오` (보안을 위해 EC2를 통해서만 접근)
   * **VPC 보안 그룹**: `신규 생성` (이름: `rds-mysql-sg`)

### 3.2 RDS 보안 그룹(Security Group) 인바운드 규칙 설정
* **RDS 보안 그룹 (`rds-mysql-sg`)** ➔ **인바운드 규칙 편집**:
  * **유형**: `MySQL/Aurora (3306)`
  * **소스**: `사용자 지정` ➔ **EC2의 보안 그룹 ID (`sg-xxxxxxxx`)** 지정
  *(EC2 인스턴스에서 오는 3306 포트 트래픽만 허용하도록 제한)*

---

## 4. 3단계: AWS EC2 인프라 구축 및 보안 그룹 설정

### 4.1 EC2 인스턴스 생성
1. **AWS Console** ➔ **EC2** ➔ **인스턴스 시작** 클릭
2. **이름**: `pipeline-web-server`
3. **애플리케이션 및 OS 이미지**: `Ubuntu Server 22.04 LTS (64비트 x86)`
4. **인스턴스 유형**: `t2.micro` 또는 `t3.micro`
5. **키 페어(Key Pair)**: `.pem` 키 생성 및 안전한 장소에 다운로드 (`pipeline-key.pem`)
6. **네트워크 설정 (보안 그룹 `ec2-web-sg`)**:
   * **SSH (포트 22)**: 내 IP (또는 특정 관리자 IP)
   * **HTTP (포트 80)**: 위치 상관없이 (0.0.0.0/0)
   * **HTTPS (포트 443)**: 위치 상관없이 (0.0.0.0/0)

### 4.2 탄력적 IP (Elastic IP) 할당
1. EC2 네트워크 & 보안 ➔ **탄력적 IP** ➔ **탄력적 IP 주소 할당**
2. 생성된 탄력적 IP 선택 ➔ **주소 연결** ➔ 방금 만든 EC2 인스턴스 선택
*(EC2를 재부팅해도 IP가 바뀌지 않도록 고정 IP를 부여합니다.)*

---

## 5. 4단계: EC2 서버 환경 세팅 및 프로젝트 배포

### 5.1 EC2 인스턴스 SSH 접속
```bash
# 로컬 터미널 (키 페어 파일 권한 축소 필수)
chmod 400 pipeline-key.pem
ssh -i "pipeline-key.pem" ubuntu@<EC2_탄력적_IP>
```

### 5.2 EC2 패키지 및 서버 환경 구축
```bash
# 패키지 목록 업데이트 & 필수 시스템 의존성 설치
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev default-libmysqlclient-dev build-essential pkg-config git nginx redis-server

# Redis 서비스 활성화 및 시작
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### 5.3 Git 프로젝트 소스코드 소환 및 가상환경 세팅
```bash
# 프로젝트 위치 디렉토리 생성 및 클론
cd /home/ubuntu
git clone https://github.com/YourOrg/YourRepo.git project
cd project

# Python 가상환경 구축
python3 -m venv venv
source venv/bin/activate

# 의존성 패키지 일괄 설치
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

---

## 6. 5단계: Django ↔ AWS RDS 마이그레이션 실행

### 6.1 환경 변수 관리 (`.env` 작성)
소스코드 내 보안 유출을 막기 위해 EC2 서버의 프로젝트 루트 경로에 `.env` 파일을 작성합니다.

```bash
nano .env
```

`.env` 파일 내용:
```env
DEBUG=False
SECRET_KEY=your_production_django_secret_key
ALLOWED_HOSTS=<EC2_탄력적_IP>,yourdomain.com,www.yourdomain.com

# RDS Database Configuration
DB_NAME=pipeline_db
DB_USER=admin
DB_PASSWORD=your_rds_password
DB_HOST=pipeline-rds-mysql.xxxxxx.ap-northeast-2.rds.amazonaws.com
DB_PORT=3306

# Redis Cache & Celery Broker
REDIS_URL=redis://127.0.0.1:6379/0
```

### 6.2 RDS에 초기 데이터베이스 생성 (RDS MySQL 접속)
```bash
# EC2 내부에서 RDS MySQL로 직접 접속
mysql -h pipeline-rds-mysql.xxxxxx.ap-northeast-2.rds.amazonaws.com -u admin -p

# 데이터베이스 생성
CREATE DATABASE pipeline_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

### 6.3 Django `settings.py` 환경변수 적용
```python
import os
from pathlib import Path
import environ

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
```

### 6.4 AWS RDS로 마이그레이션 및 Static 수집
```bash
# 마이그레이션 적용
python manage.py migrate

# 정적 파일(Swagger UI, Admin CSS 등) 수집
python manage.py collectstatic --noinput

# RDS 관리자 계정 생성
python manage.py createsuperuser
```

---

## 7. 6단계: Nginx + Gunicorn 연동 (Web Server & WSGI)

### 7.1 Gunicorn systemd 서비스 등록
Gunicorn 프로세스가 서버 재부팅 시에도 자동으로 실행되도록 백그라운드 서비스 데몬으로 등록합니다.

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

`/etc/systemd/system/gunicorn.service` 파일 내용:
```ini
[Unit]
Description=gunicorn daemon for Django Pipeline Project
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/project
ExecStart=/home/ubuntu/project/venv/bin/gunicorn           --access-logfile -           --workers 3           --bind unix:/home/ubuntu/project/gunicorn.sock           config.wsgi:application

[Install]
WantedBy=multi-user.target
```

```bash
# Gunicorn 데몬 시작 및 자동 실행 설정
sudo systemctl daemon-reload
sudo systemctl start gunicorn
sudo systemctl enable gunicorn

# Gunicorn 소켓 생성 및 상태 확인
sudo systemctl status gunicorn
ls -l /home/ubuntu/project/gunicorn.sock
```

### 7.2 Nginx 환경 설정
```bash
sudo nano /etc/nginx/sites-available/pipeline
```

`/etc/nginx/sites-available/pipeline` 파일 내용:
```nginx
server {
    listen 80;
    server_name <EC2_탄력적_IP> yourdomain.com www.yourdomain.com;

    client_max_body_size 50M;

    location /static/ {
        alias /home/ubuntu/project/staticfiles/;
    }

    location /media/ {
        alias /home/ubuntu/project/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/ubuntu/project/gunicorn.sock;
    }
}
```

```bash
# 심볼릭 링크 생성 (설정 활성화)
sudo ln -s /etc/nginx/sites-available/pipeline /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Nginx 구문 검사 및 재시작
sudo nginx -t
sudo systemctl restart nginx
```

---

## 8. 7단계: Celery & Redis 비동기 워커 Background 서비스 등록

AI Agent 연동 및 긴 작업(기획서/요구사항정의서 생성) 처리를 위해 Celery 워커를 데몬으로 등록합니다.

```bash
sudo nano /etc/systemd/system/celery.service
```

`/etc/systemd/system/celery.service` 파일 내용:
```ini
[Unit]
Description=Celery Worker Service for Pipeline System
After=network.target redis-server.service

[Service]
Type=forking
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/project
EnvironmentFile=/home/ubuntu/project/.env
ExecStart=/home/ubuntu/project/venv/bin/celery -A config worker --loglevel=INFO --detach

[Install]
WantedBy=multi-user.target
```

```bash
# Celery 데몬 실행
sudo systemctl daemon-reload
sudo systemctl start celery
sudo systemctl enable celery
```

---

## 9. 8단계: 도메인 연결 및 SSL(HTTPS) 적용

### 9.1 Route53 또는 도메인 등록업체 DNS 설정
* **A 레코드**: `@` ➔ `<EC2_탄력적_IP>`
* **A 레코드**: `www` ➔ `<EC2_탄력적_IP>`

### 9.2 Certbot 설치 및 Let's Encrypt SSL 발급
```bash
# Certbot 패키지 설치
sudo apt install -y certbot python3-certbot-nginx

# SSL 인증서 자동으로 발급 및 Nginx 설정 업데이트
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# SSL 자동 갱신 테스트
sudo certbot renew --dry-run
```

---

## 10. 트러블슈팅 & 체크리스트

| 증상 / 에러 메시지 | 원인 | 해결 방법 |
| :--- | :--- | :--- |
| `Can't connect to MySQL server on ... (110)` | RDS 보안 그룹 미설정 | RDS의 보안 그룹 인바운드 규칙에 EC2 보안 그룹(3306 포트)이 추가되었는지 확인 |
| `mysqlclient` 설치 시 `mysql_config not found` 에러 | C 컴파일 헤더 부재 | `sudo apt install default-libmysqlclient-dev build-essential` 실행 |
| `502 Bad Gateway` (Nginx) | Gunicorn 소켓 미생성 또는 권한 부족 | `gunicorn.sock` 권한 및 `systemctl status gunicorn` 서비스 상태 확인 |
| `403 Forbidden` (Static 파일) | Nginx 경로 권한 문제 | `/home/ubuntu` 디렉토리에 실행 권한 부여 (`chmod 755 /home/ubuntu`) |
| `DisallowedHost at /` | `ALLOWED_HOSTS` 누락 | `.env` 또는 `settings.py`의 `ALLOWED_HOSTS`에 도메인 및 IP 추가 |

---