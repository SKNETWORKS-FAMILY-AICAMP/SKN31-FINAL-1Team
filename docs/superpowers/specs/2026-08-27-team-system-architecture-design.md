# SKN31 1Team 시스템 아키텍처 설계

## 목적

개인 프로토타입 `heyzzabi2`의 서버 구현은 포함하지 않고, 팀 저장소의 Next.js 프론트엔드와 Django/DRF 백엔드, AI 파이프라인이 최종적으로 연결될 경계를 정의한다. 프론트엔드와 백엔드는 언어를 통일하지 않고 HTTPS, JSON, JWT, OpenAPI 계약으로 결합한다.

## 표현 기준

- 파란색 실선: 팀 저장소에 현재 코드가 존재하는 구성
- 주황색: 프론트엔드와 백엔드가 함께 맞춰야 하는 연동 영역
- 보라색 점선: 최종 서비스에 필요하지만 아직 구현 예정인 구성
- 초록색: 영속 데이터와 외부 저장소
- 번호가 붙은 굵은 화살표: 사용자가 체감하는 핵심 처리 흐름

## 계층

1. 사용자 채널: 팀장, 팀원, API 개발자와 브라우저
2. 프론트엔드: Next.js App Router, 화면 기능, 공통 API Client, JWT 상태, DTO 매핑, 문서 내보내기
3. API 백엔드: Django/DRF, SimpleJWT, CORS, OpenAPI, 도메인 ViewSet과 서비스 계층
4. 비동기·AI: Celery/Redis, LangGraph Track A/B, LLM 공급자 어댑터, Pydantic/YAML 계약
5. 데이터: 관계형 DB, S3, Qdrant, Redis
6. 운영: GitHub, CI/CD, 컨테이너·AWS, 비밀 관리, 추적·모니터링

## 핵심 인터페이스

- 프론트엔드의 모든 서버 호출은 `NEXT_PUBLIC_API_BASE_URL`을 사용하는 단일 API Client로 모은다.
- 팀 목표 OpenAPI는 `/api/` 아래 REST 엔드포인트를 정의한다. 현재 브랜치의 `/api/v1/` 구현과
  prefix를 통일한 뒤 OpenAPI 3 스키마를 단일 계약으로 사용한다.
- 로그인은 SimpleJWT의 access/refresh 토큰 계약으로 통일한다.
- 프론트의 `PM` 역할은 백엔드의 `LEADER`와 DTO 계층에서 명시적으로 매핑한다.
- 긴 AI 작업은 API 요청 안에서 직접 실행하지 않고 Celery 작업으로 발행한다.
- 생성 상태는 우선 폴링으로 조회하고, 필요할 때 SSE 또는 WebSocket을 추가한다.
- 문서 본문과 상태는 관계형 DB, 원본·산출 파일은 S3, RAG 청크와 임베딩은 Qdrant에 저장한다.

## 주요 처리 흐름

1. 사용자가 Next.js 화면에서 로그인하고 Django에 JWT를 요청한다.
2. API Client가 JWT 헤더를 포함해 회의록과 업무 데이터를 조회·저장한다.
3. 팀장이 회의록 검토 완료를 요청하면 Django가 파이프라인 상태를 기록하고 Celery 작업을 발행한다.
4. LangGraph가 회의 분석, 기획서, 요구사항, 업무 생성, 담당자 추천을 순차 수행한다.
5. 각 단계의 구조화 JSON을 Pydantic으로 검증한 뒤 DB와 파일 저장소에 기록한다.
6. 프론트엔드는 생성 상태를 조회하고 승인·반려 결과를 다음 단계 입력으로 전달한다.
7. 팀장의 최종 업무 배분 승인 후 알림을 발송하고 업무 상태를 갱신한다.
8. 사용자의 AI 질의는 Qdrant 검색 결과를 근거로 답변과 출처를 반환한다.

## 현재 코드와 목표의 차이

- 프론트엔드의 기존 Next.js `/api/...` 호출은 팀 OpenAPI 계약으로 교체해야 한다. 현재 Django의
  `/api/v1/...`와 팀 명세의 `/api/...` 중 최종 prefix를 백엔드 팀과 먼저 확정한다.
- 프론트엔드 세션 쿠키/localStorage 중심 인증은 JWT Client 구조로 변경해야 한다.
- Project, Requirement, PipelineHistory 등 프론트가 기대하지만 백엔드에 없는 모델 계약을 팀에서 확정해야 한다.
- Celery, Redis, S3, Qdrant, 실제 LLM 호출과 운영 배포는 목표 구성으로 표시한다.
- AI 그래프의 모듈 import 경로와 환경변수 공급자 설정을 정리한 뒤 Django 서비스 계층에서 호출해야 한다.

## 산출물

- `diagrams/team-system-architecture-clean.svg`: Figma 가져오기용 상세 벡터
- `diagrams/team-system-architecture-clean.png`: 빠른 검토용 미리보기
- `diagrams/team-system-architecture-clean.mmd`: 구조 변경용 Mermaid 원본
- `diagrams/team-system-architecture-clean.excalidraw`: Excalidraw 편집용 장면
