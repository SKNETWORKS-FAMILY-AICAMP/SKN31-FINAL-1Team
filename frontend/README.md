# Frontend

Next.js(App Router) 기반 프론트엔드. 회의록 → 기획서 → 요구사항정의서 → 업무배분 파이프라인 UI를
먼저 만들었던 프로토타입(heyzzabi2)에서 화면/컴포넌트만 그대로 옮겨왔습니다.

## 프레임워크 / 스택

- **Next.js 16** (App Router, Turbopack) + **React 19** + **TypeScript**
- **Tailwind CSS v4** (CSS 기반 설정 — 별도 `tailwind.config.js` 없이 `src/app/globals.css`에서 처리)
- UI: Radix UI, lucide-react, framer-motion, recharts, @dnd-kit(칸반 드래그앤드롭)
- 문서 내보내기: pptxgenjs(PPTX), xlsx(Excel) — 브라우저에서 클라이언트 사이드로 생성

## 설치

```bash
npm install
```

Python `requirements.txt`가 아니라 Node 컨벤션대로 `package.json`/`package-lock.json`으로 의존성을
관리합니다(루트의 `requirements.txt`는 `backend/`용 Python 패키지 목록입니다 — 별개).

## 실행

```bash
npm run dev
```

기본 포트 3000으로 뜹니다.

## 중요: 아직 백엔드에 연결되어 있지 않습니다

이 코드는 원래 프로토타입에서 Next.js API Route(`/api/...`, 같은 프로젝트 안의 백엔드)를 직접 호출하던
화면을 **UI만 그대로** 옮긴 것입니다. `src/app/api/**`(백엔드 라우트)와 `prisma/`(DB 스키마),
그리고 `src/lib/prisma.ts` · `requireAuth.ts` · `session.ts` · `openai.ts` · `notify.ts` ·
`overdueCheck.ts` · `passwordHash.ts`(전부 서버 전용 로직)는 옮기지 않았습니다 — 이 프로젝트의
백엔드는 Django(`backend/`)이기 때문입니다.

그래서 각 화면의 `fetch("/api/...")` 호출부는 **지금 이 상태로는 응답할 백엔드가 없어 동작하지
않습니다.** 실제 데이터 연동은 `backend/backend_readme.md`에 정의된 Django REST API
(`/api/v1/meetings`, `/api/v1/specs/{id}`, `/api/v1/assignments/...` 등)에 맞춰서 각 fetch 호출부를
교체하는 작업이 필요합니다. 어떤 파일이 어떤 API를 호출하는지 찾으려면:

```bash
# frontend/ 디렉터리에서 실행
grep -RInE 'fetch[[:space:]]*\(' src --include='*.ts' --include='*.tsx'
```

Windows PowerShell에서는 다음 명령을 사용할 수 있습니다.

```powershell
Get-ChildItem .\src -Recurse -Include *.ts,*.tsx |
  Select-String -Pattern 'fetch\s*\('
```

현재 `frontend/src`에는 `fetch()` 호출이 **19개 파일, 75곳**에 있습니다. 큰따옴표만 검색하면
작은따옴표와 템플릿 리터럴(백틱)을 놓치므로 위처럼 `fetch(` 자체를 검색해야 합니다.

## API 연동 기준: 반드시 먼저 확인할 것

프론트엔드 연동에는 서로 다른 세 가지 API 형태가 섞여 있습니다.

| 구분 | 주소 형태 | 의미 |
| --- | --- | --- |
| 기존 프론트 프로토타입 | `/api/projects`, `/api/tasks`, `/api/auth/login` | 예전 Next.js API Route 기준. 현재 저장소에는 해당 Route가 없음 |
| 현재 이 브랜치의 Django 코드 | `/api/v1/meetings/`, `/api/v1/specs/`, `/api/v1/tasks/`, `/api/v1/users/` | 지금 작업 트리에서 실제로 확인되는 제한된 API |
| [팀 API OpenAPI 명세](../docs/api/team-api.openapi.yaml) | `/api/projects/`, `/api/meetings/notes/`, `/api/requirements/`, `/api/tasks/assignments/` | 프론트엔드가 최종적으로 맞출 **목표 API 계약**. 20개 경로, 40개 작업 정의 |

이 문서에서는 제공받은 `API (2).yaml`의 저장소 사본을 **목표 계약**으로 사용합니다. 다만 YAML에 있다고 해서 현재
실행 중인 백엔드에 이미 구현되었다는 뜻은 아닙니다. 연동 직전에는 반드시 백엔드 Swagger에서 같은
경로와 요청/응답 필드가 실제로 노출되는지 확인해야 합니다.

```text
목표 명세 예시: http://localhost:8000/api/schema/swagger-ui/
현재 브랜치:    http://localhost:8000/api/v1/swagger/
```

> Django REST Framework는 기본적으로 URL 끝의 `/`를 사용합니다. 예를 들어 `/api/projects`가 아니라
> `/api/projects/`로 호출합니다. `POST` 요청에서 슬래시가 빠지면 리다이렉트 과정에서 요청 본문이
> 유실되거나 오류가 날 수 있습니다.

## 팀 목표 API 전체 목록 (`API (2).yaml` 기준)

### 0단계: 공통 코드와 프로젝트

| Method | Endpoint | 용도 |
| --- | --- | --- |
| `GET` | `/api/common/codes/?group_code=DEPT` | 부서, 직급, 상태 등 공통 코드 조회 |
| `GET` | `/api/projects/` | 프로젝트 목록 조회 |
| `POST` | `/api/projects/` | 프로젝트 생성 |
| `GET` | `/api/projects/{id}/` | 프로젝트 상세 조회 |
| `PUT` | `/api/projects/{id}/` | 프로젝트 전체 수정 |
| `PATCH` | `/api/projects/{id}/` | 프로젝트 일부 수정 |
| `DELETE` | `/api/projects/{id}/` | 프로젝트 삭제 |
| `GET` | `/api/projects/{project_id}/history/` | 프로젝트 파이프라인 이력 조회 |

### 1단계: 회의록과 기획서

| Method | Endpoint | 용도 |
| --- | --- | --- |
| `GET` | `/api/meetings/notes/` | 회의록 목록 조회 |
| `POST` | `/api/meetings/notes/` | 회의록 등록 |
| `GET` | `/api/meetings/notes/{meeting_id}/` | 회의록 상세 조회 |
| `PUT` | `/api/meetings/notes/{meeting_id}/` | 회의록 전체 수정 |
| `PATCH` | `/api/meetings/notes/{meeting_id}/` | 회의록 일부 수정 |
| `DELETE` | `/api/meetings/notes/{meeting_id}/` | 회의록 삭제 |
| `POST` | `/api/meetings/notes/{id}/analyze/` | AI 회의록 분석 및 기획서 초안 생성 |
| `GET` | `/api/meetings/specs/` | 기획서 목록 조회 |
| `POST` | `/api/meetings/specs/` | 기획서 직접 작성 |
| `GET` | `/api/meetings/specs/{spec_id}/` | 기획서 상세 조회 |
| `PUT` | `/api/meetings/specs/{spec_id}/` | 기획서 전체 수정 |
| `PATCH` | `/api/meetings/specs/{spec_id}/` | 기획서 일부 수정 |
| `PATCH` | `/api/meetings/specs/{id}/review/` | 검토 의견 저장 및 기획서 승인 |

### 2단계: 요구사항 정의

| Method | Endpoint | 용도 |
| --- | --- | --- |
| `GET` | `/api/requirements/` | 요구사항 정의서 목록 조회 |
| `POST` | `/api/requirements/` | 요구사항 정의서 생성 |
| `GET` | `/api/requirements/{id}/` | 요구사항 정의서와 하위 항목 조회 |
| `PUT` | `/api/requirements/{id}/` | 요구사항 정의서 전체 수정 |
| `PATCH` | `/api/requirements/{id}/` | 요구사항 정의서 일부 수정 |
| `DELETE` | `/api/requirements/{id}/` | 요구사항 정의서 삭제 |
| `POST` | `/api/requirements/{id}/extract/` | 기획서 기반 AI 요구사항 항목 추출 |
| `GET` | `/api/requirements/items/` | 세부 요구사항 항목 목록 조회 |
| `POST` | `/api/requirements/items/` | 세부 요구사항 항목 직접 추가 |

### 3단계: 업무 배정

| Method | Endpoint | 용도 |
| --- | --- | --- |
| `GET` | `/api/tasks/assignments/` | 업무 배정 목록 조회 |
| `POST` | `/api/tasks/assignments/` | 업무 수동 배정 |
| `GET` | `/api/tasks/assignments/{id}/` | 업무 상세 조회 |
| `PUT` | `/api/tasks/assignments/{id}/` | 업무 전체 수정 |
| `PATCH` | `/api/tasks/assignments/{id}/` | 업무 일부 수정 |
| `DELETE` | `/api/tasks/assignments/{id}/` | 업무 삭제 |
| `PATCH` | `/api/tasks/assignments/{id}/status/` | 승인·진행·완료 상태 변경 |
| `POST` | `/api/tasks/auto-assign/` | AI 자동 업무 배정 |

### 사용자

| Method | Endpoint | 용도 |
| --- | --- | --- |
| `GET` | `/api/users/` | 사용자·개발자 목록 조회 |
| `GET` | `/api/users/me/` | 현재 로그인 사용자 상세 프로필 조회 |

`API (2).yaml`에는 JWT Bearer 인증 사용이 명시되어 있지만 로그인·토큰 갱신 API 자체는 포함되어
있지 않습니다. 프론트 작업 전에 백엔드 담당자와 아래 주소를 확정해야 합니다.

- 로그인: 예) `POST /api/users/login/` 또는 `POST /api/token/`
- 토큰 갱신: 예) `POST /api/users/refresh/` 또는 `POST /api/token/refresh/`
- 로그아웃: 서버 차단 목록을 사용할지, 프론트에서 토큰만 제거할지

현재 브랜치 코드에는 `POST /api/v1/users/login/`, `POST /api/v1/users/refresh/`가 구현되어 있습니다.
목표 명세에도 이 두 API를 포함할지 팀 합의가 필요합니다.

### 핵심 요청 Body (`API (2).yaml` 기준)

| 작업 | 최소 요청 필드 | 주요 선택 필드 |
| --- | --- | --- |
| 프로젝트 생성 | `name` | `description`, `owner` |
| 회의록 생성 | `title`, `content` | `meeting_date`, `attendees` |
| 기획서 작성 | `meeting`, `title` | `overview`, `background`, `target_scope`, `key_features`, `status_code`, `review_comment` |
| 요구사항 정의서 생성 | `spec`, `title` | `version`, `description` |
| 요구사항 항목 생성 | `req_def`, `req_code`, `req_name`, `description` | `priority_code`, `difficulty`, `category` |
| 업무 수동 배정 | `req_item`, `assigned_user`, `task_title`, `task_description` | `start_date`, `due_date` |
| 업무 상태 변경 | `status` | `PENDING_APPROVAL`, `APPROVED`, `IN_PROGRESS`, `COMPLETED` 중 하나 |

회의록 등록 예시:

```json
{
  "title": "2026-08-27 스프린트 회의",
  "content": "회의 원문 또는 정리된 회의 내용",
  "meeting_date": "2026-08-27",
  "attendees": "팀장, 프론트엔드, 백엔드, AI 담당"
}
```

업무 수동 배정 예시:

```json
{
  "req_item": 12,
  "assigned_user": 4,
  "task_title": "로그인 API 연동",
  "task_description": "SimpleJWT 로그인과 사용자 조회 화면을 연결한다.",
  "start_date": "2026-08-28",
  "due_date": "2026-08-30"
}
```

### YAML에서 백엔드 팀이 보완해야 할 명세 오류·누락

첨부 YAML을 그대로 코드 생성에 사용하기 전에 다음 항목을 먼저 수정해야 합니다.

1. `/api/meetings/notes/{id}/analyze/`, `/api/meetings/specs/{id}/review/`,
   `/api/requirements/{id}/extract/`, `/api/tasks/assignments/{id}/status/`는 URL에는 `{id}`만 있는데
   path parameter로 `id`와 `pk`가 동시에 선언되어 있습니다. 하나로 통일해야 합니다.
2. AI 분석, 요구사항 추출, 자동 배정 API의 요청 Body가 명세에 없습니다. 빈 Body인지,
   `project_id`·`spec_id`·옵션 값을 받는지 정의해야 합니다.
3. `SpecDocument`에 문자열 `id`와 정수 `spec_id`가 동시에 있습니다. 프론트가 어떤 값을 URL ID로
   사용해야 하는지 확정해야 합니다.
4. 로그인·refresh·로그아웃 경로와 Token 요청/응답 schema가 빠져 있습니다.
5. 사용자 목록은 있지만 생성·수정·삭제·비밀번호 변경 API가 없습니다.
6. 목록 API가 단순 배열인지 DRF 페이지네이션의 `{count, next, previous, results}`인지 명확히 해야 합니다.
7. 기획서·요구사항·업무 반려에 필요한 상태 코드와 `review_comment`/반려 사유 규칙을 확정해야 합니다.
8. API 서버 주소(`servers:`)가 없습니다. 로컬·개발·운영 서버 URL을 명세에 추가하는 것이 좋습니다.

## 화면·파일별 fetch 교체표

상태 의미:

- **교체 가능**: 목표 YAML에 대응 API가 있음
- **DTO 변환 필요**: API는 있지만 프론트가 기대하는 필드명이 다름
- **백엔드 확인 필요**: 목표 YAML에 정확히 대응하는 API가 없음

| 프론트 파일 | 기존 호출 | 목표 API | 상태와 작업 |
| --- | --- | --- | --- |
| `src/lib/auth.tsx` | `/api/auth/login`, `/api/auth/me`, `/api/auth/logout`, `/api/auth/onboarding` | 로그인 API 미정, `GET /api/users/me/` | 로그인·refresh 계약 확정 필요. 세션 쿠키 방식에서 JWT Bearer 방식으로 변경 |
| `src/app/(dashboard)/project/new/page.tsx` | `POST /api/projects` | `POST /api/projects/` | 교체 가능. 응답의 `{success, data}` 래퍼 사용 여부 확인 |
| `src/app/(dashboard)/projects/[id]/page.tsx` | 프로젝트·사용자·업무 CRUD | `/api/projects/{id}/`, `/api/users/`, `/api/tasks/assignments/` | DTO 변환 필요 |
| `src/app/(dashboard)/documents/page.tsx` | `/api/projects/current`, 프로젝트 하위 문서 생성·승인·반려 | 프로젝트, 회의록, 기획서, 요구사항 API | 단일 `ProjectDocument` UI 모델을 3개 백엔드 리소스로 조합해야 함 |
| `src/components/projects/NewDocumentModal.tsx` | 프로젝트 생성, 파일 파싱, 프로젝트 하위 문서 생성 | `/api/projects/`, `/api/meetings/notes/` | 텍스트 회의록 등록은 교체 가능. 파일 파싱 API는 백엔드 확인 필요 |
| `src/components/documents/TaskAssignmentPanel.tsx` | 업무 추출·배정, 사용자, 업무 수정 | `/api/requirements/{id}/extract/`, `/api/tasks/auto-assign/`, `/api/tasks/assignments/{id}/` | 교체 가능하지만 `doc.id`가 아니라 요구사항 ID를 사용해야 함 |
| `src/app/(dashboard)/tasks/page.tsx` | `/api/tasks`, `/api/projects`, `/api/users` | `/api/tasks/assignments/`, `/api/projects/`, `/api/users/` | DTO·상태 코드 변환 필요 |
| `src/components/layout/KanbanBoard.tsx` | 업무 CRUD, 담당자 추천, 승인·반려 | `/api/tasks/assignments/`, `/api/tasks/assignments/{id}/status/`, `/api/tasks/auto-assign/` | 개별 추천·반려 API가 별도인지 백엔드 확인 필요 |
| `src/app/(dashboard)/approvals/page.tsx` | 승인 대기 목록, 개별 승인·반려 | `/api/tasks/assignments/`, `/api/tasks/assignments/{id}/status/` | `status=PENDING_APPROVAL` 필터 지원 여부와 반려 상태 코드 확인 필요 |
| `src/components/projects/TaskDetailModal.tsx` | 업무 상세 수정 | `/api/tasks/assignments/{id}/` | 교체 가능, 필드 매핑 필요 |
| `src/app/(dashboard)/members/page.tsx` | 사용자 목록·생성·수정·삭제·비밀번호 초기화·권한 변경 | `/api/users/` | 목록만 명세됨. 나머지 관리 API는 백엔드 추가 필요 |
| `src/app/(dashboard)/profile/page.tsx` | 프로필 조회·수정·비밀번호 변경 | `/api/users/me/` | 조회는 가능. 수정·비밀번호 변경 메서드는 명세에 추가 필요 |
| `src/app/(dashboard)/history/page.tsx` | `/api/projects/current`의 중첩 데이터로 이력 재구성 | `/api/projects/{project_id}/history/` | 전용 이력 API로 교체 가능 |
| `src/components/dashboard/OverviewView.tsx` | `/api/dashboard` | 프로젝트·업무·이력 API 조합 또는 집계 API | 대시보드 집계 API가 없어 백엔드 추가 또는 프론트 조합 필요 |
| `src/components/dashboard/AnalyticsView.tsx` | `/api/analytics` | 대응 없음 | 백엔드 집계 API 추가 필요 |
| `src/components/layout/NotificationBell.tsx` | 알림 조회·읽음 처리 | 대응 없음 | 알림 API 또는 WebSocket/SSE 계약 추가 필요 |
| `src/app/(dashboard)/settings/page.tsx` | 현재 프로젝트·설정 수정 | `/api/projects/{id}/` | 프로젝트 필드만 수정 가능. 별도 settings 필드는 명세 추가 필요 |
| `src/app/(dashboard)/ai-hub/page.tsx` | `/api/chat` | 대응 없음 | AI Q&A API와 스트리밍 방식 결정 필요 |
| `src/app/(dashboard)/ai-agents/page.tsx` | chat, research, AI 업무 추출 | 요구사항 추출·자동 배정 일부만 대응 | chat/research API는 추가 필요 |

## 프론트 DTO에서 반드시 바꿔야 하는 필드

프론트 타입을 백엔드 응답 타입과 같은 것으로 가정하면 화면 곳곳에서 `undefined`가 발생합니다.
API 응답 DTO(Data Transfer Object, 서버 응답 모양)와 화면 모델을 분리하고 mapper 함수로 변환해야 합니다.

| 개념 | 기존 프론트 값 | 목표 API 값 | 변환 규칙 |
| --- | --- | --- | --- |
| 사용자 역할 | `PM`, `MEMBER` | `role_code` 또는 팀 코드 값 | 팀장 코드를 `PM`으로, 나머지를 `MEMBER`로 변환 |
| 사용자 이름 | `name` | `first_name`, `full_name`, `username` | 사용할 필드를 팀에서 하나로 확정 |
| 사용자 ID | 문자열 | 정수 | URL 작성 시 문자열 변환, 내부 타입은 `number` 권장 |
| 완료 상태 | `DONE` | `COMPLETED` | UI mapper에서 `COMPLETED → DONE` 변환 또는 UI 상태를 통일 |
| 업무 제목 | `title` | `task_title` | mapper에서 변환 |
| 업무 설명 | `description` | `task_description` | mapper에서 변환 |
| 담당자 | `{id, name}` 객체 | `assigned_user`, `assigned_user_name` | 화면 객체로 재조립 |
| 기획서 내용 | `proposalContent` JSON 문자열 | `overview`, `background`, `target_scope`, `key_features` | 화면 템플릿 모델로 조립 |
| 요구사항 내용 | `reqSpecContent` JSON 문자열 | `RequirementDefinition.items[]` | 정의서와 항목 배열을 화면 모델로 조립 |
| 응답 포장 | `{success, data}` | YAML상 객체 또는 배열 직접 반환 | `data.success` 검사를 제거하고 HTTP 상태로 성공 여부 판단 |

## 실제 교체 방법

### 1. API 기본 주소를 환경 변수로 분리

`frontend/.env.local`에 다음 값을 추가합니다. 팀 서버 주소가 정해지면 값만 교체합니다.

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`.env.local`은 개인 환경 파일이므로 실제 비밀값을 넣거나 Git에 커밋하지 않습니다. 프론트에서 공개되어도
되는 API 주소만 `NEXT_PUBLIC_` 변수로 둡니다.

### 2. 공통 API Client를 한 번만 작성

각 컴포넌트가 URL, JWT, 에러 처리를 반복하지 않도록 `src/lib/api/client.ts`를 만들고 모든 화면에서
이 함수를 사용합니다.

```ts
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const accessToken =
    typeof window === "undefined" ? null : localStorage.getItem("access_token");

  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(
      errorBody?.detail ?? errorBody?.message ?? `API 요청 실패 (${response.status})`,
    );
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
```

파일 다운로드는 JSON 응답이 아니므로 별도 함수에서 `response.blob()`으로 처리합니다.

### 3. JWT 로그인·조회 흐름을 맞춤

로그인 주소가 확정되었다고 가정한 예시입니다. 현재 Django SimpleJWT는 일반적으로 `username`과
`password`를 받으므로 프론트의 `email` 값을 그대로 보내면 실패할 수 있습니다.

```ts
type TokenPair = { access: string; refresh: string };

const tokens = await apiFetch<TokenPair>("/api/users/login/", {
  method: "POST",
  body: JSON.stringify({ username: userId, password }),
});

localStorage.setItem("access_token", tokens.access);
localStorage.setItem("refresh_token", tokens.refresh);

const me = await apiFetch<UserDetailDto>("/api/users/me/");
```

`401 Unauthorized`가 오면 refresh 토큰으로 access 토큰을 한 번 갱신하고 원 요청을 한 번만 재시도합니다.
refresh도 실패하면 토큰을 제거하고 `/login`으로 이동합니다. 무한 재시도를 막기 위해 재시도 여부 플래그가
필요합니다.

### 4. DTO mapper를 둠

```ts
type TaskAssignmentDto = {
  id: number;
  task_title: string;
  task_description: string;
  assigned_user: number;
  assigned_user_name: string;
  status: "PENDING_APPROVAL" | "APPROVED" | "IN_PROGRESS" | "COMPLETED";
  start_date: string | null;
  due_date: string | null;
  updated_at: string;
};

function toTask(dto: TaskAssignmentDto) {
  return {
    id: String(dto.id),
    title: dto.task_title,
    description: dto.task_description,
    assignee: {
      id: String(dto.assigned_user),
      name: dto.assigned_user_name,
    },
    status: dto.status === "COMPLETED" ? "DONE" : dto.status,
    startDate: dto.start_date,
    dueDate: dto.due_date,
    updatedAt: dto.updated_at,
  };
}
```

mapper를 두면 백엔드 필드가 바뀌어도 화면 컴포넌트 10곳을 고치는 대신 mapper 한 곳만 고치면 됩니다.

### 5. 화면 하나씩 세로로 연결

전체 `fetch`를 한 번에 바꾸지 말고 다음 순서로 한 화면의 조회·생성·수정·오류 처리를 끝낸 뒤 다음으로
넘어갑니다.

1. 로그인: 토큰 발급 → `/api/users/me/` → 새로고침 후 로그인 유지
2. 프로젝트: 목록 → 생성 → 상세 → 수정
3. 회의록: 등록 → 상세 → AI 분석
4. 기획서: 조회 → 수정 → 검토·승인
5. 요구사항: 정의서 조회 → AI 항목 추출 → 항목 확인
6. 업무 배정: 자동 배정 → 목록 → 승인 → 진행 → 완료
7. 이력: 프로젝트 타임라인 확인
8. 직원·대시보드·알림·AI Q&A처럼 아직 API가 부족한 화면

예를 들어 기존 코드는 다음과 같습니다.

```ts
const res = await fetch("/api/tasks");
const json = await res.json();
if (json.success) setTasks(json.data);
```

목표 API 연결 후에는 다음 형태가 됩니다.

```ts
const rows = await apiFetch<TaskAssignmentDto[]>("/api/tasks/assignments/");
setTasks(rows.map(toTask));
```

### 6. 요청마다 확인할 체크리스트

- Swagger에서 Method·URL·요청 Body·응답 Body를 직접 확인했는가?
- URL 끝에 `/`가 있는가?
- `Authorization: Bearer <access-token>` 헤더가 들어갔는가?
- `GET` 목록 응답이 배열인지 `{results: []}` 페이지네이션 형태인지 확인했는가?
- 프론트의 `{success, data}` 가정이 남아 있지 않은가?
- `snake_case` 응답을 화면의 `camelCase`로 mapper에서 변환했는가?
- `400`, `401`, `403`, `404`, `500` 오류를 사용자에게 구분해 보여주는가?
- AI 작업이 오래 걸리면 로딩 상태, 중복 클릭 방지, polling 또는 작업 상태 조회가 있는가?
- 삭제·승인 버튼을 중복 클릭해도 같은 요청이 여러 번 실행되지 않는가?
- 브라우저 개발자 도구 Network 탭에서 요청 URL과 응답을 확인했는가?

## 백엔드 팀과 추가로 확정해야 하는 API

아래 항목은 현재 프론트에 화면이 있지만 `API (2).yaml`에는 충분한 계약이 없습니다.

1. JWT 로그인·refresh·로그아웃과 토큰 저장 정책
2. 사용자 생성·수정·삭제·비밀번호 초기화·권한 변경
3. 알림 목록·읽음·전체 읽음과 실시간 전달 방식(WebSocket/SSE/polling)
4. 대시보드 요약·분석 집계 API
5. AI Hub 채팅·대화 이력·스트리밍 응답 API
6. Research Agent 실행·목록·삭제 API
7. 회의 파일 업로드·텍스트 추출 API와 허용 확장자·최대 용량
8. 기획서·요구사항 파일 다운로드 API
9. 기획서·요구사항·업무의 반려 상태와 반려 사유 필드
10. 업무 담당자 추천과 자동 배정의 차이, 재실행 정책
11. 프로젝트 `current`의 의미 또는 기본 프로젝트 선택 규칙
12. 목록 API 페이지네이션·검색·정렬·상태 필터 규칙

## 자주 발생하는 연동 오류

| 증상 | 원인 | 확인 방법 |
| --- | --- | --- |
| 브라우저에서 404 | 예전 Next.js `/api/...`를 호출하거나 prefix가 다름 | Network 탭의 Request URL과 Swagger 경로 비교 |
| `POST`만 실패 | Django URL 끝 `/` 누락 | URL을 `/api/.../` 형태로 수정 |
| 401 | 토큰 없음·만료·헤더 형식 오류 | `Authorization: Bearer ...` 확인 |
| 403 | 로그인은 됐지만 역할·소유권 권한 부족 | 로그인 사용자와 백엔드 permission 확인 |
| CORS 오류 | Django 허용 origin에 Next.js 주소가 없음 | `http://localhost:3000` 허용 여부 확인 |
| 화면이 비어 있음 | 응답 배열을 `{success, data}`로 읽거나 필드명이 다름 | 실제 JSON과 mapper 입력 타입 비교 |
| 날짜가 이상함 | UTC ISO 문자열을 로컬 시간으로 잘못 해석 | `created_at`, `updated_at`과 타임존 확인 |
| 파일 다운로드 깨짐 | JSON client로 파일 응답을 처리함 | `blob()`과 `Content-Disposition` 사용 |
| AI 버튼 중복 실행 | 처리 중 버튼 비활성화·멱등성 키 없음 | 요청 중 `disabled`, 백엔드 중복 방지 확인 |

## 연동 완료 판정

화면에 데이터가 한 번 보이는 것만으로 완료 처리하지 않습니다. 각 화면마다 다음을 확인합니다.

1. 정상 조회·등록·수정·삭제 또는 승인 흐름
2. 토큰 만료 후 refresh 또는 로그인 이동
3. 권한 없는 계정의 403 처리
4. 빈 목록·느린 응답·서버 오류 UI
5. 새로고침 후 상태 복구
6. 백엔드 DB에서 실제 데이터 변경 확인
7. 프론트 TypeScript 검사와 빌드 통과

```bash
npm run lint
npm run build
```

README에 적힌 경로와 실제 Swagger가 다르면 README를 믿고 강제로 연결하지 말고, Swagger/YAML/현재
백엔드 코드 중 어느 것을 최종 계약으로 사용할지 먼저 팀에서 확정한 뒤 한쪽을 수정합니다.

## 옮겨온 화면 구성 (참고용)

- `src/app/(auth)/` — 로그인, 온보딩
- `src/app/(dashboard)/` — 대시보드, 회의록/기획서/요구사항정의서/업무배분(`documents`), 칸반형
  업무 관리(`tasks`), 프로젝트 상세, 직원 관리(`members`), 이력(`history`), 설정 등
- `src/components/` — 위 화면들이 쓰는 컴포넌트 일체(칸반 보드, 문서 상세/모달, 대시보드 위젯 등)
- `src/lib/` — 서버 의존성 없는 순수 유틸/타입/상수만 (auth 컨텍스트, 문서 템플릿 타입, PPTX/Excel
  내보내기, 날짜/지연 판정 로직 등)
