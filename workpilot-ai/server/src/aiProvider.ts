import type {
  AIProvider,
  AssigneeRecommendation,
  DelayReason,
  DeliverableResult,
  Member,
  Project,
  ProgressSignal,
  ProjectContext,
  RequestAnalysis,
  SiblingDeliverable,
  Task,
  TaskDraft,
} from "./types.js";

// ── MockAIProvider ───────────────────────────────────────────────────
// 기획안 7.3절: 실제 LLM 호출 없이 키워드/규칙 기반으로 AIProvider와 동일한
// 응답 스키마를 반환한다. ClaudeAIProvider로 교체해도 호출부는 변경되지 않는다.

interface FeatureRule {
  keywords: string[];
  tasks: TaskDraft[];
}

// 도메인 키워드 → 표준 기능 분해 규칙. 매칭되는 키워드가 없으면 제네릭 3단계
// (설계/구현/테스트)로 폴백한다.
const FEATURE_RULES: FeatureRule[] = [
  {
    keywords: ["회원가입", "가입", "signup", "register"],
    tasks: [
      {
        title: "회원가입 API 설계/구현",
        description: "회원 정보 검증, 저장, 중복 체크를 포함한 회원가입 API",
        requiredSkills: ["Backend", "DB"],
        estimateHours: 16,
        dependsOnTitles: [],
      },
      {
        title: "회원가입 UI 구현",
        description: "회원가입 폼, 입력 검증, 에러 처리 화면",
        requiredSkills: ["Frontend"],
        estimateHours: 12,
        dependsOnTitles: ["회원가입 API 설계/구현"],
      },
      {
        title: "이메일 인증 연동",
        description: "가입 확인 이메일 발송 및 인증 처리",
        requiredSkills: ["Backend", "외부연동"],
        estimateHours: 8,
        dependsOnTitles: ["회원가입 API 설계/구현"],
      },
    ],
  },
  {
    keywords: ["로그인", "login", "인증"],
    tasks: [
      {
        title: "로그인 연동",
        description: "세션/토큰 기반 로그인 처리 및 회원가입과의 연동",
        requiredSkills: ["Backend", "Frontend"],
        estimateHours: 8,
        dependsOnTitles: ["회원가입 API 설계/구현"],
      },
    ],
  },
  {
    keywords: ["결제", "payment", "pg"],
    tasks: [
      {
        title: "결제 API 연동",
        description: "PG사 연동 및 결제 승인/취소 처리",
        requiredSkills: ["Backend", "외부연동"],
        estimateHours: 20,
        dependsOnTitles: [],
      },
      {
        title: "결제 UI 구현",
        description: "결제 수단 선택, 결제 진행/완료 화면",
        requiredSkills: ["Frontend"],
        estimateHours: 12,
        dependsOnTitles: ["결제 API 연동"],
      },
    ],
  },
  {
    keywords: ["검색", "search"],
    tasks: [
      {
        title: "검색 API 구현",
        description: "키워드 검색, 필터링, 페이지네이션",
        requiredSkills: ["Backend", "DB"],
        estimateHours: 14,
        dependsOnTitles: [],
      },
      {
        title: "검색 UI 구현",
        description: "검색창, 결과 리스트, 필터 UI",
        requiredSkills: ["Frontend"],
        estimateHours: 10,
        dependsOnTitles: ["검색 API 구현"],
      },
    ],
  },
  {
    keywords: ["알림", "notification", "푸시"],
    tasks: [
      {
        title: "알림 발송 시스템 구현",
        description: "이벤트 기반 알림 큐 및 발송 처리",
        requiredSkills: ["Backend"],
        estimateHours: 12,
        dependsOnTitles: [],
      },
    ],
  },
  {
    keywords: ["게시판", "게시글", "bbs", "board"],
    tasks: [
      {
        title: "게시판 API 구현",
        description: "게시글 목록 조회, 작성, 삭제를 처리하는 API",
        requiredSkills: ["Backend", "DB"],
        estimateHours: 14,
        dependsOnTitles: [],
      },
      {
        title: "게시판 UI 구현",
        description: "게시글 목록, 작성 폼, 삭제 버튼이 있는 화면",
        requiredSkills: ["Frontend"],
        estimateHours: 12,
        dependsOnTitles: ["게시판 API 구현"],
      },
    ],
  },
];

const TEST_KEYWORDS = ["테스트", "test", "qa", "검증"];

function uniq<T>(arr: T[]): T[] {
  return Array.from(new Set(arr));
}

function escapeHtmlText(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function guessFormFields(text: string): Array<{ label: string; type: string }> {
  const lower = text.toLowerCase();
  const fields: Array<{ label: string; type: string }> = [];
  if (lower.includes("이메일") || lower.includes("email")) fields.push({ label: "이메일", type: "email" });
  if (lower.includes("비밀번호") || lower.includes("password")) fields.push({ label: "비밀번호", type: "password" });
  if (lower.includes("이름") || lower.includes("name")) fields.push({ label: "이름", type: "text" });
  if (lower.includes("검색") || lower.includes("search")) fields.push({ label: "검색어", type: "text" });
  if (lower.includes("전화") || lower.includes("phone")) fields.push({ label: "전화번호", type: "tel" });
  return fields;
}

const SHARED_PREVIEW_CSS = `
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; padding: 24px;
    font-family: "Segoe UI", sans-serif; background: #16161f; color: #e8e8f0;
  }
  .wrap { max-width: 480px; margin: 0 auto; }
  .card { background: #1e1e2e; border: 2px solid #3a3a52; box-shadow: 3px 3px 0 #0a0a14; padding: 24px; }
  h1 { font-size: 18px; margin: 0 0 6px; color: #06d6a0; }
  p.note { font-size: 11px; color: #9a9ab0; margin: 0 0 18px; }
  p.hint { font-size: 13px; color: #cfcfe0; }
  label { display: block; font-size: 12px; color: #9a9ab0; margin-bottom: 12px; }
  input, textarea { width: 100%; padding: 9px; margin-top: 4px; background: #12121c; border: 1px solid #3a3a52; color: #e8e8f0; font-size: 13px; font-family: inherit; }
  button { padding: 10px; margin-top: 6px; background: #06d6a0; border: none; color: #0a0a14; font-weight: bold; cursor: pointer; }
  button:hover { opacity: 0.9; }
`;

/** 브라우저 안에서 실제로 저장되는 게 목적이므로 항상 이 형태의 localStorage 키를 쓴다
 * (백엔드 없이 새로고침해도 유지되는 "진짜 동작하는" 미리보기를 만들기 위함). */
function storageKeyFor(taskId: string): string {
  return `wp_${taskId}`;
}

const LIST_KEYWORDS = ["게시판", "게시글", "목록", "리스트", "list", "board", "게시물", "글"];

/** 목록형 화면(게시판 등) — 실제로 localStorage에 항목을 추가/조회/삭제하는 완결된 미리보기.
 * 새로고침해도 데이터가 남아 "완성된 게시판"을 그 자리에서 써볼 수 있다. */
function mockListPreview(
  task: Pick<Task, "id" | "title" | "description" | "requiredSkills">,
  project: Pick<Project, "name" | "stack">
): DeliverableResult {
  const key = storageKeyFor(task.id);
  const content = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>${escapeHtmlText(task.title)}</title>
<style>
${SHARED_PREVIEW_CSS}
  .item-list { list-style: none; margin: 16px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .item { background: #12121c; border: 1px solid #3a3a52; padding: 10px; display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
  .item strong { display: block; font-size: 13px; color: #e8e8f0; }
  .item p { margin: 4px 0 0; font-size: 12px; color: #9a9ab0; white-space: pre-wrap; }
  .item .meta { font-size: 10px; color: #6a6a80; margin-top: 6px; }
  .item button.del { background: transparent; border: 1px solid #ef476f; color: #ef476f; padding: 4px 8px; font-size: 11px; flex-shrink: 0; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>${escapeHtmlText(task.title)}</h1>
      <p class="note">${escapeHtmlText(project.name)} · Mock 미리보기 — 실제로 브라우저 localStorage에 저장됩니다. 새로고침해도 유지됩니다.</p>
      <form id="f">
        <label>제목<input type="text" id="field_title" placeholder="제목 입력" required /></label>
        <label>내용<textarea id="field_content" rows="3" placeholder="내용 입력"></textarea></label>
        <button type="submit">등록</button>
      </form>
      <ul class="item-list" id="list"></ul>
      <p class="hint" id="empty" style="display:none;">아직 등록된 항목이 없습니다. 위에서 첫 항목을 등록해보세요.</p>
    </div>
  </div>
  <script>
    var KEY = ${JSON.stringify(key)};
    function load() { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } }
    function save(items) { localStorage.setItem(KEY, JSON.stringify(items)); }
    function render() {
      var items = load();
      var list = document.getElementById('list');
      var empty = document.getElementById('empty');
      list.innerHTML = '';
      empty.style.display = items.length ? 'none' : 'block';
      items.slice().reverse().forEach(function (item) {
        var li = document.createElement('li');
        li.className = 'item';
        var body = document.createElement('div');
        var strong = document.createElement('strong');
        strong.textContent = item.title || '(제목 없음)';
        var p = document.createElement('p');
        p.textContent = item.content || '';
        var meta = document.createElement('div');
        meta.className = 'meta';
        meta.textContent = new Date(item.createdAt).toLocaleString();
        body.appendChild(strong); body.appendChild(p); body.appendChild(meta);
        var del = document.createElement('button');
        del.type = 'button'; del.className = 'del'; del.textContent = '삭제';
        del.addEventListener('click', function () {
          save(load().filter(function (x) { return x.id !== item.id; }));
          render();
        });
        li.appendChild(body); li.appendChild(del);
        list.appendChild(li);
      });
    }
    document.getElementById('f').addEventListener('submit', function (e) {
      e.preventDefault();
      var title = document.getElementById('field_title').value.trim();
      var content = document.getElementById('field_content').value.trim();
      if (!title) return;
      var items = load();
      items.push({ id: Date.now() + '-' + Math.random().toString(36).slice(2), title: title, content: content, createdAt: new Date().toISOString() });
      save(items);
      e.target.reset();
      render();
    });
    render();
  </script>
</body>
</html>`;

  return {
    filename: "preview.html",
    language: "html",
    content,
    summary: `${task.title}: 실제로 등록/조회/삭제가 되는 목록 화면 (localStorage 키: ${key})`,
  };
}

/** 단일 폼 화면(회원가입/로그인 등) — 제출 시 실제로 localStorage에 저장하고, 저장된 값을
 * 화면에 그대로 보여준다("가짜 성공 메시지"가 아니라 실제 데이터가 남는다). */
function mockFormPreview(
  task: Pick<Task, "id" | "title" | "description" | "requiredSkills">,
  project: Pick<Project, "name" | "stack">
): DeliverableResult {
  const fields = guessFormFields(`${task.title} ${task.description}`);
  const effectiveFields = fields.length ? fields : [{ label: "값", type: "text" }];
  const key = storageKeyFor(task.id);
  const fieldsHtml = effectiveFields
    .map(
      (f, i) =>
        `<label>${escapeHtmlText(f.label)}<input type="${f.type}" id="field_${i}" data-label="${escapeHtmlText(f.label)}" placeholder="${escapeHtmlText(f.label)} 입력" /></label>`
    )
    .join("\n        ");

  const content = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>${escapeHtmlText(task.title)}</title>
<style>
${SHARED_PREVIEW_CSS}
  .wrap { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 48px); }
  .card { width: 340px; }
  .saved { margin-top: 14px; padding: 10px; background: #12201c; border: 1px solid #06d6a0; font-size: 12px; display: none; }
  .saved div { margin-bottom: 2px; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>${escapeHtmlText(task.title)}</h1>
      <p class="note">${escapeHtmlText(project.name)} · Mock 미리보기 — 실제로 브라우저 localStorage에 저장됩니다.</p>
      <form id="f">
        ${fieldsHtml}
        <button type="submit">저장</button>
      </form>
      <div class="saved" id="saved"></div>
    </div>
  </div>
  <script>
    var KEY = ${JSON.stringify(key)};
    var savedBox = document.getElementById('saved');
    function renderSaved() {
      var data = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (!data) { savedBox.style.display = 'none'; return; }
      savedBox.innerHTML = '<strong>✓ 저장된 값 (localStorage)</strong>';
      Object.keys(data).forEach(function (k) {
        var d = document.createElement('div');
        d.textContent = k + ': ' + data[k];
        savedBox.appendChild(d);
      });
      savedBox.style.display = 'block';
    }
    document.getElementById('f').addEventListener('submit', function (e) {
      e.preventDefault();
      var data = {};
      document.querySelectorAll('#f input').forEach(function (el) { data[el.dataset.label] = el.value; });
      localStorage.setItem(KEY, JSON.stringify(data));
      renderSaved();
    });
    renderSaved();
  </script>
</body>
</html>`;

  return {
    filename: "preview.html",
    language: "html",
    content,
    summary: `${task.title}: 실제로 localStorage에 저장되는 입력 화면 (필드: ${effectiveFields.map((f) => f.label).join(", ")}, 키: ${key})`,
  };
}

/** MockAIProvider용 — 실제 LLM 없이도 "브라우저에서 바로 열리는, 실제로 동작하는 화면"을
 * 보여줄 수 있도록 목록형(게시판 등)/폼형(회원가입 등)을 구분해서 만든다. */
function mockHtmlPreview(
  task: Pick<Task, "id" | "title" | "description" | "requiredSkills">,
  project: Pick<Project, "name" | "stack">
): DeliverableResult {
  const lower = `${task.title} ${task.description}`.toLowerCase();
  const isList = LIST_KEYWORDS.some((k) => lower.includes(k.toLowerCase()));
  return isList ? mockListPreview(task, project) : mockFormPreview(task, project);
}

export class MockAIProvider implements AIProvider {
  async analyzeRequest(input: string, context: ProjectContext): Promise<RequestAnalysis> {
    const lower = input.toLowerCase();
    const stackNote =
      context.stack.length === 0
        ? ["기술 스택 미지정 — 프로젝트 컨텍스트(기존 스택) 확인 필요"]
        : [];
    const matched = FEATURE_RULES.filter((rule) =>
      rule.keywords.some((k) => lower.includes(k.toLowerCase()))
    );
    const includeTestPhase = TEST_KEYWORDS.some((k) =>
      lower.includes(k.toLowerCase())
    );

    const included: string[] = [];
    matched.forEach((rule) =>
      rule.tasks.forEach((t) => included.push(t.title))
    );
    if (includeTestPhase) {
      included.push("단위 테스트 작성", "통합 테스트 및 QA");
    }

    if (included.length === 0) {
      // 폴백: 어떤 도메인 키워드도 못 찾으면 요청 원문을 기능명으로 삼아
      // 설계/구현/테스트 3단계로 제네릭 분해한다.
      included.push(
        `${input.trim()} — 설계`,
        `${input.trim()} — 구현`,
        `${input.trim()} — 테스트`
      );
    }

    const uncertain: string[] = [];
    if (lower.includes("회원가입") && !lower.includes("소셜")) {
      uncertain.push("소셜 로그인 포함 여부");
      uncertain.push("비밀번호 정책(길이/특수문자 등)");
    }
    if (matched.length > 0 && !includeTestPhase) {
      uncertain.push("테스트 범위(단위/통합) 포함 여부");
    }

    return {
      rawText: input,
      included: uniq(included),
      uncertain: uniq([...uncertain, ...stackNote]),
      excluded: [],
      matchedKeywords: uniq(matched.flatMap((r) => r.keywords)),
    };
  }

  async decomposeIntoTasks(analysis: RequestAnalysis): Promise<TaskDraft[]> {
    const lower = analysis.rawText.toLowerCase();
    const matched = FEATURE_RULES.filter((rule) =>
      rule.keywords.some((k) => lower.includes(k.toLowerCase()))
    );

    let drafts: TaskDraft[];
    if (matched.length > 0) {
      drafts = matched.flatMap((r) => r.tasks);
    } else {
      const base = analysis.rawText.trim() || "신규 기능";
      drafts = [
        {
          title: `${base} — 설계`,
          description: "요구사항을 바탕으로 한 상세 설계",
          requiredSkills: ["Backend"],
          estimateHours: 8,
          dependsOnTitles: [],
        },
        {
          title: `${base} — 구현`,
          description: "설계에 따른 기능 구현",
          requiredSkills: ["Backend", "Frontend"],
          estimateHours: 16,
          dependsOnTitles: [`${base} — 설계`],
        },
        {
          title: `${base} — 테스트`,
          description: "기능 검증 테스트",
          requiredSkills: ["Test"],
          estimateHours: 6,
          dependsOnTitles: [`${base} — 구현`],
        },
      ];
    }

    const includeTestPhase = TEST_KEYWORDS.some((k) =>
      lower.includes(k.toLowerCase())
    );
    if (includeTestPhase && matched.length > 0) {
      const allTitles = drafts.map((d) => d.title);
      drafts.push(
        {
          title: "단위 테스트 작성",
          description: "각 기능 단위 테스트 작성",
          requiredSkills: ["Test"],
          estimateHours: 8,
          dependsOnTitles: allTitles,
        },
        {
          title: "통합 테스트 및 QA",
          description: "전체 기능 통합 테스트 및 QA",
          requiredSkills: ["QA"],
          estimateHours: 12,
          dependsOnTitles: ["단위 테스트 작성"],
        }
      );
    }

    return drafts;
  }

  async recommendAssignee(
    task: Pick<Task, "requiredSkills" | "title">,
    members: Member[]
  ): Promise<AssigneeRecommendation[]> {
    const candidates = members.filter((m) => !m.isLead);
    const pool = candidates.length > 0 ? candidates : members;

    const scored = pool.map((m) => {
      const overlap = task.requiredSkills.filter((s) =>
        m.skills.includes(s)
      ).length;
      const skillMatch =
        task.requiredSkills.length === 0
          ? 0.5
          : overlap / task.requiredSkills.length;
      const loadPenalty = Math.min(m.currentLoadHours / 80, 1); // 80h 이상이면 포화로 간주
      const perfKey = task.requiredSkills[0] ?? "general";
      const pastPerf = m.pastPerformance[perfKey] ?? 0.6;

      const w1 = 0.5;
      const w2 = 0.3;
      const w3 = 0.2;
      const score = w1 * skillMatch + w2 * (1 - loadPenalty) + w3 * pastPerf;

      const reasonParts = [
        `스킬 매칭 ${Math.round(skillMatch * 100)}%`,
        `현재 부하 ${m.currentLoadHours}h`,
        `과거 수행 지표 ${pastPerf.toFixed(2)}`,
      ];

      return {
        memberId: m.id,
        score: Math.round(score * 1000) / 1000,
        reason: reasonParts.join(", "),
      };
    });

    return scored.sort((a, b) => b.score - a.score);
  }

  async analyzeDelayRisk(
    task: Task,
    signals: ProgressSignal[],
    nowIso: string
  ): Promise<{ reason: DelayReason; message: string; proposedAction: string } | null> {
    if (task.status === "done" || !task.plannedEnd) return null;
    const now = new Date(nowIso).getTime();
    const plannedEnd = new Date(task.plannedEnd).getTime();

    if (now > plannedEnd && task.status !== "delayed") {
      const overdueHours = Math.round((now - plannedEnd) / 3600000);
      return {
        reason: "estimate_exceeded",
        message: `예상 완료일을 ${overdueHours}시간 초과했습니다.`,
        proposedAction: `일정을 ${Math.ceil(
          overdueHours / 8
        )}일 순연하거나, 지원 인력 투입을 검토하세요.`,
      };
    }

    const lastSignal = signals
      .filter((s) => s.taskId === task.id)
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0];
    if (task.status === "active" && lastSignal) {
      const idleHours =
        (now - new Date(lastSignal.timestamp).getTime()) / 3600000;
      if (idleHours >= 72) {
        return {
          reason: "signal_stalled",
          message: `${Math.round(
            idleHours
          )}시간째 진행 신호(커밋/PR/상태 업데이트)가 없습니다.`,
          proposedAction: "담당자에게 진행 상황 확인이 필요합니다.",
        };
      }
    }

    return null;
  }

  async summarizeMeeting(rawText: string) {
    const lines = rawText
      .split(/\n+/)
      .map((l) => l.trim())
      .filter(Boolean);

    const decisions: string[] = [];
    const actionItems: string[] = [];
    const risks: string[] = [];

    for (const line of lines) {
      const stripped = line.replace(/^[-*·]\s*/, "");
      if (/결정|확정|채택/.test(line)) decisions.push(stripped);
      else if (/액션|todo|할 일|담당|진행할/i.test(line))
        actionItems.push(stripped);
      else if (/이슈|리스크|우려|확인 필요|미결/.test(line))
        risks.push(stripped);
      else decisions.push(stripped); // 분류 안 되면 결정 사항으로 폴백
    }

    return { decisions, actionItems, risks };
  }

  // 규칙 기반이라 실제 코드를 "짤" 수는 없다 — 대신 무엇을 구현해야 하는지 정리한
  // 구현 계획 문서를 만들어서, 실 LLM 연동 전에도 파이프라인/파일 서빙이 동일하게 동작하게 한다.
  // 단, Frontend/UI 작업은 "실제 구동되는 화면을 보고 싶다"는 요구를 Mock 모드에서도 어느 정도
  // 보여줄 수 있게 간단한 정적 HTML 미리보기를 만든다(진짜 로직은 없고 폼 흉내만 낸다).
  async generateDeliverable(
    task: Pick<Task, "id" | "title" | "description" | "requiredSkills">,
    project: Pick<Project, "name" | "stack">,
    siblingDeliverables: SiblingDeliverable[]
  ): Promise<DeliverableResult> {
    if (task.requiredSkills.some((s) => /frontend|ui/i.test(s))) {
      return mockHtmlPreview(task, project);
    }
    const content = [
      `# ${task.title}`,
      "",
      `> 이 파일은 실제 LLM(Claude/OpenAI) 없이 MockAIProvider가 만든 구현 계획입니다.`,
      `> ANTHROPIC_API_KEY 또는 OPENAI_API_KEY를 설정하면 실제 코드가 생성됩니다.`,
      "",
      `## 프로젝트`,
      `${project.name}${project.stack.length ? ` (스택: ${project.stack.join(", ")})` : ""}`,
      "",
      `## 설명`,
      task.description || "(설명 없음)",
      "",
      `## 필요 스킬`,
      task.requiredSkills.length ? task.requiredSkills.map((s) => `- ${s}`).join("\n") : "- (명시 없음)",
      "",
      `## 연동해야 할 다른 작업의 결과물`,
      siblingDeliverables.length
        ? siblingDeliverables.map((s) => `- **${s.title}**: ${s.summary}`).join("\n")
        : "- (아직 없음 — 이 작업이 먼저 진행됨)",
      "",
      `## 구현 체크리스트 (예시)`,
      `- [ ] 요구사항에 맞는 인터페이스/스키마 정의`,
      `- [ ] 핵심 로직 구현`,
      `- [ ] 에러/예외 케이스 처리`,
      `- [ ] 테스트 작성`,
    ].join("\n");
    const summary = `${task.title}: ${task.description || "구현 계획 문서 (Mock)"}`.slice(0, 160);
    return { filename: "plan.md", language: "markdown", content, summary };
  }

  async suggestNextSteps(
    project: Pick<Project, "name" | "requestText" | "stack">,
    _completedTasks: Pick<Task, "title" | "description">[]
  ): Promise<string[]> {
    const lower = project.requestText.toLowerCase();
    const alreadyCovered = new Set(
      FEATURE_RULES.filter((r) => r.keywords.some((k) => lower.includes(k.toLowerCase()))).flatMap(
        (r) => r.keywords
      )
    );
    const suggestions = FEATURE_RULES.filter((r) => !r.keywords.some((k) => alreadyCovered.has(k))).map(
      (r) => `${r.keywords[0]} 기능 추가해줘`
    );
    suggestions.push("성능/보안 점검하고 개선해줘");
    return suggestions.slice(0, 4);
  }
}
