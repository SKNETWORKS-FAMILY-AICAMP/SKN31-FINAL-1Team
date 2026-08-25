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
grep -rn 'fetch("/api' src/
```

## 옮겨온 화면 구성 (참고용)

- `src/app/(auth)/` — 로그인, 온보딩
- `src/app/(dashboard)/` — 대시보드, 회의록/기획서/요구사항정의서/업무배분(`documents`), 칸반형
  업무 관리(`tasks`), 프로젝트 상세, 직원 관리(`members`), 이력(`history`), 설정 등
- `src/components/` — 위 화면들이 쓰는 컴포넌트 일체(칸반 보드, 문서 상세/모달, 대시보드 위젯 등)
- `src/lib/` — 서버 의존성 없는 순수 유틸/타입/상수만 (auth 컨텍스트, 문서 템플릿 타입, PPTX/Excel
  내보내기, 날짜/지연 판정 로직 등)
