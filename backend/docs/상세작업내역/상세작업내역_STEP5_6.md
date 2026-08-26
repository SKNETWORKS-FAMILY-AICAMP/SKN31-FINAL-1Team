### STEP 5 & 6: 고도화, 테스트 및 API 문서화
* **작업일 : 2026-08-26**

* **API 문서화**
  * `drf-spectacular` 활용, Swagger UI 자동 생성하여 프론트엔드 팀에 제공
  * 접속 엔드포인트 정리:
    * Swagger UI: http://127.0.0.1:8000/api/docs/swagger/
    * ReDoc: http://127.0.0.1:8000/api/docs/redoc/
    * JSON/YAML Schema: http://127.0.0.1:8000/api/schema/
    
* **비동기 처리 & 캐싱**
  * Redis를 통한 세션 상태 저장 및 Celery를 이용한 대화 요약/통계 비동기 처리
  * 산출물: Redis, Celery 연동

* **테스트 & 배포 준비**
  * PyTest 기반 주요 API 및 LLM 파이프라인 단위 테스트 작성
  * Dockerfile 및 `docker-compose.yml` 작성