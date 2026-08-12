# WorkPilot AI

`WorkPilot_AI_기획안.docx`(기획안) 로드맵을 실제로 동작하는 코드로 구현한 것입니다.

업무 요청(자연어) 한 줄만 입력하면 그 이후 AI 분석 → 작업 분해(WBS) → 담당자 추천/자동 배정 →
일정 생성 → 진행/완료 → 지연 감지/알림까지 **전부 자동으로 이어서 실행됩니다.** PM이 개입하는
지점은 최초 업무 지시뿐입니다. 픽셀 오피스에서는 배정된 팀원이 실제 pixel-agents 스프라이트로
앉아서, 작업이 진행되면 타이핑 애니메이션으로, 지연되면 경고 말풍선으로 상태를 보여줍니다.

## 실제 결과물 생성

작업이 착수(active)되는 순간, 활성화된 AI 프로바이더가 그 작업을 실제로 구현한 파일 하나를
만들어 `server/output/<projectId>/<taskId>-<filename>` 에 저장합니다(파이프라인/자동 착수와
동일한 지점에서 트리거되므로 오토파일럿이 자동으로 만듭니다). 작업 카드에 뜨는 **결과물** 링크로
바로 열어볼 수 있고(`/files/<projectId>/<filename>`), 서버 재시작 없이 새로고침만으로 반영됩니다.

- Claude/OpenAI가 켜져 있으면 실제로 동작하는 코드 파일을 씁니다(언어/파일명은 모델이 작업
  내용을 보고 스스로 판단).
- Mock 모드에서는 실제 코드를 "짤" 수는 없으니, 대신 그 작업을 어떻게 구현할지 정리한
  `plan.md` 구현 계획 문서를 만듭니다 — 파이프라인/파일 서빙 동작은 동일하게 확인할 수 있습니다.
- 작업당 한 번만 생성됩니다(같은 작업에 진행 신호가 여러 번 와도 중복 호출하지 않음).
- **작업끼리 서로 연결되도록** 두 가지를 자동으로 합니다:
  1. 이미 완료된 형제 작업의 결과물 요약(노출한 API 경로/컴포넌트명 등)을 다음 작업 생성
     프롬프트에 함께 넣어서, 새로 지어내지 말고 기존 인터페이스를 그대로 갖다 쓰게 유도합니다.
  2. 분해된 작업이 2개 이상이면 **"메인 화면/통합 연결"** 작업을 자동으로 추가합니다.
     이 작업은 다른 모든 작업에 의존하도록 설정되므로(오토파일럿의 의존관계 게이트 덕분에)
     나머지가 전부 끝난 뒤에야 착수되고, 그 시점엔 모든 형제 결과물 요약이 갖춰져 있어
     실제로 그것들을 잇는 코드를 시도합니다.
  - 다만 이건 "같은 코드베이스를 읽고 쓰는" 진짜 통합이 아니라 텍스트 요약 기반 힌트라는 한계는
    있습니다 — 그래도 아무 맥락 없이 각자 짜는 것보다는 훨씬 일관성 있는 결과가 나옵니다.

## 결과물 미리보기 (실제 구동 화면)

**Frontend/UI 작업**은 코드가 아니라 브라우저에서 그 자리에서 바로 열리는 **완결된 단일 .html
파일**로 생성됩니다(별도 빌드 없이 인라인 `<style>`/`<script>`만으로 동작, 폼 제출 같은 실제
인터랙션 포함). 결과물을 클릭하면 뜨는 모달이 이 파일을 iframe으로 그대로 그려서 **"미리보기"
탭**에서 실제 구동 화면을 볼 수 있고, **"코드" 탭**에서 소스도 확인할 수 있습니다.

- Mock 모드에서도 동작합니다 — 진짜 로직은 없지만 제목/설명에서 그럴듯한 입력 필드를 추측해
  정적 HTML 미리보기를 만듭니다.
- **Backend/DB/Test 같은 작업은 화면이 없으므로** 이 미리보기가 뜨지 않고 코드만 보여줍니다 —
  API 핸들러나 테스트 코드는 애초에 브라우저에 그릴 화면이 없다는 게 이유입니다.

### 결과물이 실제로 "동작"하는지 — localStorage 기반 영속 저장

서버 프로세스나 실제 DB 없이도, Frontend/UI 결과물은 브라우저 `localStorage`를 실제 저장소로
사용해 **진짜로 등록/조회/삭제가 되도록** 생성됩니다(가짜 "성공했습니다" 메시지가 아님).

- 각 작업은 자기 전용 키 `wp_<taskId>` 하나만 사용합니다 — 같은 프로젝트의 다른 화면과 데이터가
  섞이지 않습니다.
- **게시판/목록형**(제목·설명에 "게시판/게시글/목록/리스트/board" 등이 들어가면) — 등록 폼 +
  목록 + 삭제 버튼이 실제로 동작하는 화면이 생성됩니다. 새로고침해도 등록한 글이 남아 있습니다.
- **폼형**(회원가입 등) — 제출한 값이 `localStorage`에 저장되고, 화면에 저장된 값을 그대로
  다시 보여줍니다.
- 예: "게시판을 만들어줘"라고 요청하면 `게시판 API 구현` → `게시판 UI 구현` → `메인 화면/통합
  연결` 세 작업으로 자동 분해되고, UI 작업의 결과물을 열면 그 자리에서 글을 쓰고 지울 수 있는
  게시판을 바로 써볼 수 있습니다.
- 한계: 이건 **브라우저 하나(그 결과물 파일)에 한정된 저장소**입니다 — 실제 서버/DB가 아니라서
  다른 사람과 데이터가 공유되지 않고, 다른 브라우저에서 열면 빈 상태로 시작합니다. 여러 사람이
  공유하는 진짜 백엔드가 필요하면 AI가 생성한 백엔드 코드를 실제로 실행하는 단계(아직 미구현,
  더 신중한 논의가 필요한 영역)가 필요합니다.

## 다음 단계 자동 추천

프로젝트의 모든 작업이 완료되면(오토파일럿이 더 할 일이 없으면), AI가 완료된 작업들을 근거로
다음에 하면 좋을 일을 3~4개 자동으로 제안합니다(예: "로그인 기능 추가해줘"). "1. 업무 요청"
패널 하단에 뜨고, 둘 중 하나로 이어갈 수 있습니다.

- **제안 버튼 클릭** — 그 문구 그대로 새 라운드가 시작됩니다.
- **직접 타이핑** — 하단 입력창에 원하는 다음 지시를 자유롭게 써서 진행 버튼을 누르면 됩니다.

둘 다 **새 프로젝트를 만들지 않고 같은 프로젝트에 작업을 이어 붙입니다** — 팀/오피스는 그대로
유지되고, 요청 이력이 "1. 업무 요청" 패널에 계속 쌓입니다. 새로 추가된 작업도 분해→통합
작업 자동 추가→추천→자동 승인까지 그대로 자동 진행됩니다.

## AI 연동

Claude와 OpenAI(GPT) 둘 다 지원합니다(`server/src/aiProviderClaude.ts` / `aiProviderOpenAI.ts`).
어떤 프로바이더를 쓸지는 `server/src/aiProviderFactory.ts`가 고릅니다:

1. `WORKPILOT_AI_PROVIDER=claude|openai|mock` 이 지정돼 있으면 그걸 그대로 씁니다.
2. 지정이 없으면 있는 키를 자동으로 씁니다: `ANTHROPIC_API_KEY` 우선, 없으면 `OPENAI_API_KEY`.
3. 둘 다 없으면 `MockAIProvider`(규칙 기반)로 동작합니다 — 설치 없이 바로 데모 가능.

API 호출이 실패하거나(네트워크 오류, 401 등) JSON 파싱이 깨져도 항상 Mock으로 안전하게 폴백해
파이프라인이 죽지 않습니다. 지연 감지(`analyzeDelayRisk`)는 순수 날짜 계산이라 어느 프로바이더를
쓰든 LLM을 부르지 않고 결정론적 로직을 그대로 씁니다.

### 키 설정 — `server/.env` 파일 (권장)

`server/.env.example`을 복사해서 `server/.env`로 만들고 값을 채우면, 서버 시작 시 자동으로
읽어 들입니다(`server/src/env.ts`, 외부 의존성 없는 자체 구현 — `.env`는 `.gitignore`에 걸려
커밋되지 않습니다).

```bash
cp workpilot-ai/server/.env.example workpilot-ai/server/.env
# server/.env 파일을 열어 ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 채우기
```

셸 환경변수로 직접 설정해도 동일하게 동작합니다(둘 다 있으면 셸 환경변수가 우선):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# 또는
export OPENAI_API_KEY=sk-...
export WORKPILOT_AI_PROVIDER=openai   # 둘 다 있을 때 OpenAI를 강제하고 싶다면
```

모델을 바꾸고 싶으면 `WORKPILOT_CLAUDE_MODEL`(기본 `claude-sonnet-5`) /
`WORKPILOT_OPENAI_MODEL`(기본 `gpt-4o-mini`)을 설정하세요.

헤더의 배지(`● Claude API 연동됨` / `● OpenAI API 연동됨` / `○ Mock(rule-based) 모드`)로
현재 어떤 프로바이더가 살아있는지 바로 확인할 수 있습니다.

## 실행 방법

Node.js 18 이상만 있으면 됩니다. 소스를 고쳤다면 다시 빌드해야 합니다(둘 다 프로젝트 루트의
TypeScript로 컴파일, 별도 `npm install` 불필요 — 루트 저장소의 `typescript`를 그대로 씁니다).

```bash
npx tsc -p workpilot-ai/server/tsconfig.json
npx tsc -p workpilot-ai/web/tsconfig.json
cd workpilot-ai/server
node dist/index.js
# [WorkPilot AI] server listening on http://localhost:4100
```

브라우저에서 `http://localhost:4100` 접속.

포트를 바꾸려면: `PORT=4200 node dist/index.js` (Windows PowerShell: `$env:PORT=4200; node dist/index.js`)

## 써보는 방법

1. 요청 입력창에 `회원가입 시스템을 만들고 테스트까지 진행해줘` 입력 → **요청 분석**
2. 그 즉시 AI가 회원가입 API/UI/이메일 인증/테스트 등으로 자동 분해하고, 담당자를 추천해 바로
   배정까지 끝냅니다 — 픽셀 오피스에 팀원이 배정된 좌석에 나타납니다.
3. **오토파일럿**이 4초마다 가상 시계를 3시간씩 흘리며, 선행 작업이 끝난 순서대로 다음 작업을
   자동 착수시키고, 예상 소요시간(±난수)만큼 지나면 자동 완료 처리합니다. 캐릭터가 idle → 타이핑
   애니메이션으로 바뀌는 걸 그냥 지켜보면 됩니다.
4. 일부 작업은 일부러 예상보다 오래 걸리도록 설계돼 있어(0.7x~1.5x), 진행 중 예상 기한을 넘기면
   자동으로 지연 알림이 뜨고 캐릭터 위에 경고 말풍선이 표시됩니다. 더 빨리 보고 싶으면 가상 시계
   패널의 "빨리감기" 버튼으로 강제 전진할 수 있습니다.
5. 회의 요약 패널에 텍스트 입력 → **요약 반영** → 액션 아이템이 신규 작업으로 자동 생성되고,
   그 작업도 곧바로 추천/배정까지 자동으로 이어집니다.
6. 수동 개입이 필요하면(재배정 등) 작업 카드의 담당자 드롭다운/승인/거절 버튼을 그대로 쓸 수 있습니다.

## 구조

```
server/   Node.js + TypeScript 백엔드 (외부 런타임 의존성 없음, fetch만 사용)
  src/env.ts              server/.env 로더 (dotenv 없이 자체 구현, 다른 모든 import보다 먼저 실행)
  src/types.ts            도메인 타입 + AIProvider 인터페이스(전부 Promise 반환)
  src/aiProvider.ts        MockAIProvider(규칙 기반 폴백)
  src/aiProviderClaude.ts  ClaudeAIProvider(Anthropic Messages API)
  src/aiProviderOpenAI.ts  OpenAIProvider(OpenAI Chat Completions API, response_format=json_object)
  src/aiProviderFactory.ts WORKPILOT_AI_PROVIDER/키 유무로 claude·openai·mock 중 실제 사용할 프로바이더 선택
  src/llmJson.ts           LLM 응답에서 JSON을 관대하게 파싱하는 공용 유틸(코드펜스/설명문 대비)
  src/pipeline.ts          분해/추천/자동승인/진행/완료/지연감지/회의요약 — 실제 오케스트레이션 로직
  src/routes.ts            REST 라우트 (pipeline.ts를 얇게 감쌈)
  src/autopilot.ts         "지시 이외엔 전부 자동"의 핵심 — 백그라운드 틱으로 작업을 자동 착수/완료/지연감지
  src/scheduler.ts         일정 계산 (의존관계 기반 Critical Path 단순화 버전)
  src/store.ts             인메모리 스토어 (+ 가상 시계)
  src/http.ts / httpServer.ts   프레임워크 없는 라우터 + 정적 파일 서빙

web/      브라우저 네이티브 ES 모듈 프런트엔드 (React/번들러 없음)
  src/office/sprites.ts   pixel-agents 실제 캐릭터 스프라이트 시트(char_0..5.png) 렌더링
  src/office/canvas.ts    오피스 캔버스: 좌석 배치, 상태 FSM, 말풍선
  src/ui/panels.ts        요청/파이프라인/작업(WBS+Gantt바)/알림/회의 패널 렌더링
  src/main.ts             이벤트 위임 + REST 폴링(2초) 기반 상태 갱신 + AI모드 배지/가상시계 표시
  public/assets/characters/  pixel-agents(webview-ui)에서 그대로 가져온 스프라이트 PNG
  public/                컴파일된 정적 산출물 (index.html, styles.css, js/)
```

## 알려진 단순화 (MVP 범위)

- **DB 없음**: 인메모리 저장이라 서버를 재시작하면 데이터가 초기화됩니다.
- **실시간 갱신은 WebSocket이 아니라 2초 폴링**입니다.
- **1 작업시간 = 1 시간(wall-clock, 가상 시계 기준)**으로 일정을 계산합니다. 실제 8시간/근무일,
  휴가/캘린더 반영은 이후 단계.
- **가상 시계 기반 자동 진행**입니다. 실제 커밋/PR 신호(Phase 2 로드맵)가 아니라 오토파일럿의
  시뮬레이션으로 진행/완료가 결정됩니다 — Git/PR 연동이 들어오면 그 신호가 우선하도록 바꾸면 됩니다.
- 재현성을 위해 데모용 `/api/simulate/advance`(가상 시계 수동 전진) 엔드포인트를 남겨뒀습니다 —
  실서비스에서는 제거하거나 관리자 전용으로 제한해야 합니다.

## 다음 단계 (기획안 로드맵 기준)

- Phase 2: Git/PR 연동으로 진행 신호를 실제 커밋에서 받아오기(현재는 오토파일럿 시뮬레이션),
  WebSocket 실시간화
- Phase 4: 회의 STT 연동, 스폰/디스폰 이펙트 등 연출 고도화
