### STEP 4: API View(비즈니스 로직) 및 URL 라우팅 구현
* **작업일 : 2026-08-26**

* Django 기반 프로젝트 관리 시스템의 API 구현 순서와 전체 엔드포인트 구조를 정의.

---

## 1. API 구현 순서

파이프라인 흐름(`회의록` $\rightarrow$ `기획서` $\rightarrow$ `요구사항 정의` $\rightarrow$ `업무 배정` $\rightarrow$ `통합 이력`)에 맞추어 아래 순서대로 View 및 URL 라우팅을 구축합니다.

1. **`users` & `common` 앱**: 사용자 인증, 프로필 조회, 공통 코드 메타데이터 제공 (기반 레이어)
2. **`projects` 앱**: 프로젝트 생성/조회 및 파이프라인 타임라인 이력 조회 (`/history`)
3. **`meetings` 앱**: 1단계 산출물 (회의록 작성, AI 요약, 기획서 생성 및 검토)
4. **`requirements` 앱**: 2단계 산출물 (기획서 기반 요구사항 정의서 및 세부 항목 추출)
5. **`tasks` 앱**: 3단계 산출물 (요구사항 기반 개발 업무 자동/수동 배정 및 승인)

---

## 2. 전체 API 엔드포인트 명세표

| 앱 (App) | HTTP 메서드 | 엔드포인트 URL | 설명 | 주요 액션 및 비즈니스 로직 |
|---|---|---|---|---|
| **common** | `GET` | `/api/common/codes/` | 공통 코드 목록 조회 | 부서, 직급, 상태, 기술 스택 공통 코드 조회 |
| **users** | `GET` | `/api/users/me/` | 내 정보 프로필 조회 | 현재 로그인된 사용자의 상세 프로필 및 보유 기술 반환 |
| | `GET` | `/api/users/` | 사용자/개발자 목록 조회 | 업무 자동 배정 대상 유저 목록 조회 |
| **projects** | `GET` / `POST` | `/api/projects/` | 프로젝트 목록 조회 및 생성 | 프로젝트 기본 정보 CRUD |
| | `GET` | `/api/projects/{id}/history/` | 파이프라인 전체 이력 조회 | `/history` 페이지 타임라인 이력 로그 제공 |
| **meetings** | `GET` / `POST` | `/api/meetings/notes/` | 회의록 목록 조회 및 신규 작성 | 1단계 파이프라인 시작점 |
| | `POST` | `/api/meetings/notes/{id}/analyze/` | 회의록 AI 분석/요약 실행 | 회의록 텍스트 기반 핵심 요약 및 기획 초안 데이터 생성 |
| | `GET` / `POST` | `/api/meetings/specs/` | 기획서 목록 조회 및 신규 생성 | 회의록 기반 기획서(SpecDocument) 생성 |
| | `PATCH` | `/api/meetings/specs/{id}/review/` | 기획서 검토 및 승인 | 검토 상태 변경 및 `PipelineHistory` 로그 자동 기록 |
| **requirements** | `GET` / `POST` | `/api/requirements/` | 요구사항 정의서 목록 및 생성 | 기획서 기반 2단계 요구사항 Header 생성 |
| | `POST` | `/api/requirements/{id}/extract/` | AI 요구사항 항목 자동 추출 | 기획서 내용 분석 후 `RequirementItem` 목록 자동 생성 |
| | `GET` / `POST` | `/api/requirements/items/` | 요구사항 세부 항목 CRUD | 개별 REQ 코드별 상세 명세 관리 |
| **tasks** | `GET` / `POST` | `/api/tasks/assignments/` | 배정 업무 목록 및 생성 | 요구사항 항목 기반 업무 생성 |
| | `POST` | `/api/tasks/auto-assign/` | 업무 AI 자동 배정 | 개발자 스킬셋/작업중 여부(`is_busy`) 분석 후 최적 매핑 |
| | `PATCH` | `/api/tasks/assignments/{id}/status/` | 업무 승인 및 상태 변경 | 승인 처리 및 개발 진행 상태 업데이트 |