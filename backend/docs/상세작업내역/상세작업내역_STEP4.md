# 단계별 상세 작업 내역 (Detailed Tasks)

### STEP 4: LLM 파이프라인 구축 & 스트리밍 연동 (Core LLM Integration)
* **작업일 : 2026-08-03**
* 이 단계에서는 사용자가 메시지를 보냈을 때 OpenAI API(또나 LangChain 등)를 통해 답변을 생성하고, 이를 ChatMessage DB 모델에 저장 및 반환하는 핵심 비즈니스 로직을 구축합니다.

* **LLM Client 모듈화**
  * LangChain 또는 OpenAI SDK 기반의 LLM 서비스 클래스 캡슐화
  * 이전 대화 맥락(Context)을 템플릿 프롬프트에 결합하는 로직 구현

  1) LLM 호출 서비스 파일 생성 및 작성 (llm_core/services.py)
      * 산출물: `llm_core/services.py`
  2) chat/serializers.py에 메시지 요청용 Serializer 추가
  3) chat/views.py에 LLM 메시지 전송 API 구현
  4) chat/urls.py에 엔드포인트 연결

  * 웹 연결 확인해보기
  1) 파일을 모두 저장한 뒤 서버를 재시작합니다 (python manage.py runserver)
  2) Swagger UI ([http://127.0.0.1:8000/api/v1/docs/](http://127.0.0.1:8000/api/v1/docs/))에 접속
  3) /api/v1/auth/login/에서 로그인하여 발급받은 Access Token을 우측 상단 Authorize 버튼을 눌러 등록 (<토큰>).
  4) POST /api/v1/chat/sessions/로 새 대화방을 생성 (id 확인)
  5) POST /api/v1/chat/sessions/{session_id}/completion/ 엔드포인트에서 message 항목에 질문을 넣고 실행하여 GPT의 답변이 정상적으로 돌아오는지 확인
  6) GET /api/v1/chat/sessions/ 엔드포인트에서 대화방 내역 확인
  7) DELETE /api/v1/chat/sessions/{session_id}/ 엔드포인트에서 대화방 삭제

---
* **작업일 : 2026-08-04**
* **실시간 스트리밍 API (SSE)**
  * `StreamingHttpResponse`를 활용한 Server-Sent Events (SSE) 구현
  * LLM 답변의 토큰 단위 스트리밍 응답을 React로 전달하고, 답변 완료 시 DB에 수신 메시지 저장
  * 주요 엔드포인트: `/api/v1/chat/stream/` (`text/event-stream`)

  * 백엔드 SSE 스트리밍 구현 4단계
    * [1단계: 서비스 로직] llm_core/services.py파일내부에 Generator 함수 구현  
  OpenAI 등 LLM API를 호출할 때 stream=True 옵션을 주고, 응답 조각(chunk)이 올 때마다 SSE 포맷에 맞춰 yield로 내보내는 제너레이터 함수를 만듭니다.

      * SSE 표준 데이터 포맷: data: <내용>\n\n
      * 완료 신호: 스트림 종료 시 data: [DONE]\n\n을 내보내 프론트엔드가 수신 종료를 알 수 있게 합니다.

    * [2단계: View 작성] chat/views.py 파일 내부에 ChatStreamView(APIView) 구현   
    -> 일반적인 Response 대신 Django의 StreamingHttpResponse를 사용해야 응답 데이터를 한 번에 보내지 않고 실시간 흐름으로 응답할 수 있습니다.
      * content_type='text/event-stream' 지정
      * CORS 및 버퍼링 방지 헤더 설정 (Cache-Control: no-cache, X-Accel-Buffering: no 등)

    * [3단계: URL 연결] chat/urls.py 엔드포인트
      * 프론트엔드 팀원이 접근할 수 있도록 API 경로를 추가합니다. (예: POST /api/v1/chat/stream/)

    * [4단계: 로컬 테스트] cURL / Postman 검증
      * 웹 브라우저나 cURL 명령어, 또는 Postman을 통해 한 글자씩 쪼개져 실시간으로 들어오는지 직접 테스트합니다.