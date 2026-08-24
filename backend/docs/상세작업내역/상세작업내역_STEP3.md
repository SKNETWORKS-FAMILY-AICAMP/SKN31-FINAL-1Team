# 단계별 상세 작업 내역 (Detailed Tasks)

### STEP 3: 대화 데이터 모델링 & REST API (Chat Data Module)

* **작업일 : 2026-07-31**
  * chat 앱의 대화방 & 메시지 데이터 모델 작성
  * 챗봇 서비스에서 대화 기록을 관리할 데이터베이스 테이블 생성

* **데이터 모델 설계 (ORM)**
  * chat/models.py 파일에 대화방(ChatSession)과 메시지(ChatMessage) 2개의 모델을 정의

  * `ChatSession`: 유저 Foreign Key, 세션 제목, 생성/수정일자
  * `ChatMessage`: 세션 Foreign Key, 역할(`user` / `assistant` / `system`), 메시지 본문, 생성일자
  * 산출물: `chat/models.py`

* **새로 만든 모델 DB에 적용하기**
  * DB 마이그레이션 실행
      ```
      터미널에서 아래 코드를 순차적으로 실행 
      1) python manage.py makemigrations
      2) python manage.py migrate
      ```
---

* **작업일 : 2026-08-03**

* **대화 CRUD API 개발**
  * chat 앱의 대화방 및 메시지 내역 CRUD API 구현과 Swagger 문서 반영
  * 새 대화방 생성, 목록 조회, 방 제목 변경 및 삭제 API

    * 특정 대화방의 과거 메시지 페이징 조회 API 구현
    * 주요 엔드포인트: `/api/v1/chat/rooms/`, `/api/v1/chat/rooms/{id}/messages/`

  * chat/serializers.py 생성 및 작성
  * chat/urls.py 생성 및 config/urls.py 연결
    * chat/urls.py 생성 및 작성
    * config/urls.py 파일을 열고 chat.urls 경로를 추가
      ```
      # Chat API
      path('api/v1/chat/', include('chat.urls')),
      ```
  
  * **새로 만든 모델 DB에 적용하기**
  * DB 마이그레이션 실행
      ```
      터미널에서 아래 코드를 순차적으로 실행 
      1) python manage.py makemigrations chat
      2) python manage.py migrate
      ```

  * 웹 연결 확인해보기
    * Swagger UI에 기존 /api/v1/auth/ 엔드포인트에 이어 /api/v1/chat/sessions/ 관련 대화방 CRUD API 목록이 자동으로 추가되었는지 확인
    * 터미널에서 `python manage.py runserver` 명령어를 실행(서버 연결돼있으면 ctrl + c로 종료한다음 재시작.)
    * 웹에서 `http://127.0.0.1:8000/api/v1/docs/` 접속 -> Chatbot Service API.yaml 파일 다운로드 됨.