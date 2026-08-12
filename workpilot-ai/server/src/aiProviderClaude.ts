import { MockAIProvider } from "./aiProvider.js";
import { parseJsonLoose } from "./llmJson.js";
import type {
  AIProvider,
  AssigneeRecommendation,
  DelayReason,
  DeliverableResult,
  Member,
  MeetingSummary,
  Project,
  ProgressSignal,
  ProjectContext,
  RequestAnalysis,
  SiblingDeliverable,
  Task,
  TaskDraft,
} from "./types.js";

// ── ClaudeAIProvider ─────────────────────────────────────────────────
// 기획안 7.2절: 실제 Anthropic Messages API를 호출하는 AIProvider 구현.
// 외부 SDK 의존성 없이 Node 18+ 내장 fetch만 사용한다(프로젝트의 "zero deps" 원칙 유지).
//
// 판단이 크리티컬하지 않고 순수 날짜 계산인 analyzeDelayRisk는 굳이 LLM을 태우지
// 않고 결정론적 로직(MockAIProvider와 동일)을 그대로 쓴다 — 매 autopilot tick마다
// 불필요한 API 호출/비용/지연을 만들지 않기 위함. 나머지 4개(분석/분해/추천/요약)는
// 실제 판단력이 필요한 지점이라 LLM을 호출한다.
//
// 모든 메서드는 API 실패(키 없음/네트워크 오류/JSON 파싱 실패) 시 MockAIProvider의
// 동일 메서드로 조용히 폴백한다 — 파이프라인이 절대 죽지 않는다.

const ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION = "2023-06-01";

let loggedMissingKey = false;

export class ClaudeAIProvider implements AIProvider {
  readonly kind = "claude" as const;
  private fallback = new MockAIProvider();
  private apiKey: string | undefined;
  private model: string;

  constructor(opts?: { apiKey?: string; model?: string }) {
    this.apiKey = opts?.apiKey ?? process.env.ANTHROPIC_API_KEY;
    this.model = opts?.model ?? process.env.WORKPILOT_CLAUDE_MODEL ?? process.env.WORKPILOT_AI_MODEL ?? "claude-sonnet-5";
  }

  get isLive(): boolean {
    return Boolean(this.apiKey);
  }

  private async callJson<T>(system: string, user: string, maxTokens = 1500): Promise<T | null> {
    if (!this.apiKey) {
      if (!loggedMissingKey) {
        console.warn(
          "[WorkPilot AI] ANTHROPIC_API_KEY not set — ClaudeAIProvider falling back to MockAIProvider per call."
        );
        loggedMissingKey = true;
      }
      return null;
    }
    try {
      const res = await fetch(ANTHROPIC_API_URL, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": this.apiKey,
          "anthropic-version": ANTHROPIC_VERSION,
        },
        body: JSON.stringify({
          model: this.model,
          max_tokens: maxTokens,
          system,
          messages: [{ role: "user", content: user }],
        }),
      });
      if (!res.ok) {
        console.error(`[WorkPilot AI] Claude API error ${res.status}: ${await res.text().catch(() => "")}`);
        return null;
      }
      const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
      const text = data.content?.find((c) => c.type === "text")?.text;
      if (!text) return null;
      return parseJsonLoose<T>(text);
    } catch (err) {
      console.error("[WorkPilot AI] Claude API call failed:", err);
      return null;
    }
  }

  async analyzeRequest(input: string, context: ProjectContext): Promise<RequestAnalysis> {
    const result = await this.callJson<{
      included: string[];
      uncertain: string[];
      excluded: string[];
      matchedKeywords: string[];
    }>(
      "당신은 숙련된 소프트웨어 PM입니다. 팀에게 들어온 자연어 업무 요청을 분석해 " +
        "포함 기능, 확인이 필요한 불확실한 사항, 명시적으로 제외된 사항, 매칭된 도메인 키워드를 " +
        "추려냅니다. 반드시 다른 텍스트 없이 아래 스키마의 JSON만 출력하세요:\n" +
        `{"included": string[], "uncertain": string[], "excluded": string[], "matchedKeywords": string[]}`,
      `업무 요청: "${input}"\n` +
        `현재 기술 스택: ${context.stack.length ? context.stack.join(", ") : "미지정"}\n` +
        `팀 보유 스킬: ${context.teamSkills.join(", ") || "미지정"}`
    );
    if (!result || !Array.isArray(result.included)) {
      return this.fallback.analyzeRequest(input, context);
    }
    return {
      rawText: input,
      included: result.included,
      uncertain: result.uncertain ?? [],
      excluded: result.excluded ?? [],
      matchedKeywords: result.matchedKeywords ?? [],
    };
  }

  async decomposeIntoTasks(analysis: RequestAnalysis): Promise<TaskDraft[]> {
    const result = await this.callJson<TaskDraft[]>(
      "당신은 소프트웨어 프로젝트를 WBS(작업 분해 구조)로 쪼개는 테크리드입니다. " +
        "요청 분석 결과를 받아 실행 가능한 작업 목록으로 분해하세요. 각 작업은 " +
        "title(간결한 한국어), description, requiredSkills(Backend/Frontend/DB/Test/QA/외부연동/기획 중에서), " +
        "estimateHours(현실적인 작업시간, 정수), dependsOnTitles(같은 목록 내 선행 작업의 title 배열, 없으면 빈 배열)를 " +
        "가집니다. 반드시 다른 텍스트 없이 JSON 배열만 출력하세요: " +
        `[{"title": string, "description": string, "requiredSkills": string[], "estimateHours": number, "dependsOnTitles": string[]}]`,
      `포함 기능: ${analysis.included.join(", ") || "(원문 참고)"}\n` +
        `확인 필요 사항: ${analysis.uncertain.join(", ") || "없음"}\n` +
        `원문 요청: "${analysis.rawText}"`,
      2000
    );
    if (!Array.isArray(result) || result.length === 0) {
      return this.fallback.decomposeIntoTasks(analysis);
    }
    return normalizeDrafts(result);
  }

  async recommendAssignee(
    task: Pick<Task, "requiredSkills" | "title">,
    members: Member[]
  ): Promise<AssigneeRecommendation[]> {
    const candidates = members.filter((m) => !m.isLead);
    const pool = candidates.length > 0 ? candidates : members;
    const result = await this.callJson<AssigneeRecommendation[]>(
      "당신은 팀원의 스킬/현재 부하/과거 성과를 근거로 작업 담당자를 추천하는 배정 어시스턴트입니다. " +
        "각 후보에 대해 0~1 사이 score와, 왜 그 점수인지 한국어로 짧게 설명하는 reason을 만드세요. " +
        "score가 높은 순으로 정렬해서, 다른 텍스트 없이 JSON 배열만 출력하세요: " +
        `[{"memberId": string, "score": number, "reason": string}]`,
      `작업: "${task.title}" (필요 스킬: ${task.requiredSkills.join(", ") || "명시 없음"})\n` +
        `후보 팀원:\n` +
        pool
          .map(
            (m) =>
              `- id=${m.id}, 이름=${m.name}, 스킬=${m.skills.join("/")}, 현재부하=${m.currentLoadHours}h, ` +
              `과거성과=${JSON.stringify(m.pastPerformance)}`
          )
          .join("\n")
    );
    return normalizeRecommendations(result, pool) ?? this.fallback.recommendAssignee(task, members);
  }

  // 날짜 비교만 하는 결정론적 판단이라 LLM을 호출하지 않고 규칙 기반 로직을 그대로 사용한다.
  async analyzeDelayRisk(
    task: Task,
    signals: ProgressSignal[],
    nowIso: string
  ): Promise<{ reason: DelayReason; message: string; proposedAction: string } | null> {
    return this.fallback.analyzeDelayRisk(task, signals, nowIso);
  }

  async generateDeliverable(
    task: Pick<Task, "id" | "title" | "description" | "requiredSkills">,
    project: Pick<Project, "name" | "stack">,
    siblingDeliverables: SiblingDeliverable[]
  ): Promise<DeliverableResult | null> {
    const isFrontend = task.requiredSkills.some((s) => /frontend|ui/i.test(s));
    const storageKey = `wp_${task.id}`;
    const formatInstruction = isFrontend
      ? "이 작업은 화면(프론트엔드)입니다. 사용자가 브라우저에서 그 자리에서 바로 열어 " +
        "실제로 눌러볼 수 있어야 하므로, 반드시 빌드 도구나 모듈 시스템 없이 그 자체로 동작하는 " +
        "완결된 단일 .html 파일로 작성하세요 — <style>과 <script>를 인라인으로 포함하고, " +
        "React/JSX 같은 프레임워크나 import 없이 순수 HTML/CSS/vanilla JS만 쓰세요. " +
        "백엔드 서버가 없으므로 브라우저 localStorage를 실제 저장소로 써서 진짜로 동작하게 만드세요: " +
        `키는 반드시 "${storageKey}" 하나만 쓰고, 값은 JSON으로 저장하세요. ` +
        "게시판/목록형 화면이면 배열(JSON.stringify된 항목 리스트)을 저장해서 등록·목록 조회·삭제가 " +
        "실제로 되게 하고, 새로고침해도 데이터가 남아야 합니다. 폼형 화면(회원가입 등)이면 제출된 값을 " +
        "객체로 저장하고 화면에 저장된 값을 그대로 보여주세요. 절대 '성공했습니다' 같은 가짜 메시지만 " +
        "보여주고 끝내지 마세요 — 실제로 읽고 쓰고 화면에 반영해야 합니다. filename은 .html로 끝나야 합니다."
      : "requiredSkills와 프로젝트 스택을 참고해 적절한 언어/프레임워크를 스스로 판단하세요 " +
        "(예: Backend면 Node/TS 등 — 스택이 명시돼 있으면 그걸 따르세요).";
    const result = await this.callJson<DeliverableResult>(
      "당신은 실제로 코드를 작성하는 시니어 개발자입니다. 주어진 작업을 실제로 구현하는 " +
        "파일 하나를 작성하세요(주석/설명 문서가 아니라 동작하는 코드). " +
        formatInstruction +
        " 이미 완료된 다른 작업들의 요약이 주어지면, 거기 나온 API 경로/함수명/컴포넌트명/필드명을 " +
        "그대로 갖다 써서 실제로 서로 맞물리는 코드를 작성하세요(새로 지어내지 마세요). " +
        "간결하지만 실제로 그 작업의 핵심 로직이 들어있는 완결된 파일이어야 합니다. " +
        "반드시 다른 텍스트 없이 JSON 객체만 출력하세요. 스키마: " +
        `{"filename": string(확장자 포함), "language": string, "content": string(파일 전체 내용), ` +
        `"summary": string(다른 작업이 참고할 수 있게, 이 파일이 노출하는 API 경로/함수명/컴포넌트명 등을 한두 문장으로)}`,
      `프로젝트: ${project.name}${project.stack.length ? ` (스택: ${project.stack.join(", ")})` : ""}\n` +
        `작업: "${task.title}"\n` +
        `설명: ${task.description || "(없음)"}\n` +
        `필요 스킬: ${task.requiredSkills.join(", ") || "명시 없음"}\n` +
        `이미 완료된 관련 작업 (있으면 반드시 이 인터페이스를 그대로 활용):\n` +
        (siblingDeliverables.length
          ? siblingDeliverables.map((s) => `- ${s.title}: ${s.summary}`).join("\n")
          : "(아직 없음 — 이 작업이 프로젝트에서 먼저 진행됨)"),
      3000
    );
    if (!result || !result.content || !result.filename) {
      return this.fallback.generateDeliverable(task, project, siblingDeliverables);
    }
    return {
      filename: sanitizeFilename(result.filename),
      language: result.language || "text",
      content: result.content,
      summary: result.summary || `${task.title} 구현 완료`,
    };
  }

  async suggestNextSteps(
    project: Pick<Project, "name" | "requestText" | "stack">,
    completedTasks: Pick<Task, "title" | "description">[]
  ): Promise<string[]> {
    const result = await this.callJson<{ suggestions: string[] }>(
      "당신은 숙련된 PM입니다. 방금 완료된 프로젝트를 보고, 이어서 진행하면 좋을 다음 작업을 " +
        "PM이 팀에게 지시하듯 짧은 명령문 3~4개로 제안하세요(예: \"로그인 기능 추가해줘\"). " +
        "이미 완료된 작업과 중복되지 않는, 자연스러운 다음 단계여야 합니다. " +
        "반드시 JSON 객체만 출력하세요. 스키마: " +
        `{"suggestions": string[]}`,
      `프로젝트: ${project.name}${project.stack.length ? ` (스택: ${project.stack.join(", ")})` : ""}\n` +
        `원래 요청: "${project.requestText}"\n` +
        `완료된 작업들:\n` +
        completedTasks.map((t) => `- ${t.title}: ${t.description}`).join("\n"),
      800
    );
    if (!result || !Array.isArray(result.suggestions) || result.suggestions.length === 0) {
      return this.fallback.suggestNextSteps(project, completedTasks);
    }
    return result.suggestions.slice(0, 4).map(String);
  }

  async summarizeMeeting(rawText: string): Promise<MeetingSummary> {
    const result = await this.callJson<MeetingSummary>(
      "당신은 회의록을 요약하는 어시스턴트입니다. 회의 내용에서 결정 사항(decisions), " +
        "액션 아이템(actionItems, 후속 작업으로 바로 생성될 수 있도록 실행 가능한 문장으로), " +
        "리스크/이슈(risks)를 뽑아내세요. 다른 텍스트 없이 JSON만 출력하세요: " +
        `{"decisions": string[], "actionItems": string[], "risks": string[]}`,
      rawText
    );
    if (!result || !Array.isArray(result.decisions)) {
      return this.fallback.summarizeMeeting(rawText);
    }
    return {
      decisions: result.decisions ?? [],
      actionItems: result.actionItems ?? [],
      risks: result.risks ?? [],
    };
  }
}

// aiProviderOpenAI.ts와 공유하는 정규화 헬퍼 (두 프로바이더가 같은 원본 스키마를 쓰므로 함께 둔다).
export function normalizeDrafts(result: TaskDraft[]): TaskDraft[] {
  return result.map((d) => ({
    title: String(d.title ?? "").trim() || "제목 없음",
    description: String(d.description ?? ""),
    requiredSkills: Array.isArray(d.requiredSkills) ? d.requiredSkills.map(String) : [],
    estimateHours: Number.isFinite(d.estimateHours) && d.estimateHours > 0 ? Math.round(d.estimateHours) : 8,
    dependsOnTitles: Array.isArray(d.dependsOnTitles) ? d.dependsOnTitles.map(String) : [],
  }));
}

// 모델이 만들어낸 파일명에 경로 문자(/, \, ..)가 섞여 나오는 걸 막는다 — 서버 파일 경로에 그대로 쓰인다.
export function sanitizeFilename(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? "output.txt";
  const cleaned = base.replace(/[^\w.\-]/g, "_").replace(/^\.+/, "");
  return cleaned || "output.txt";
}

export function normalizeRecommendations(
  result: AssigneeRecommendation[] | null,
  pool: Member[]
): AssigneeRecommendation[] | null {
  if (!Array.isArray(result) || result.length === 0) return null;
  const validIds = new Set(pool.map((m) => m.id));
  const filtered = result.filter((r) => validIds.has(r.memberId));
  if (filtered.length === 0) return null;
  return filtered
    .map((r) => ({ memberId: r.memberId, score: Number(r.score) || 0, reason: String(r.reason ?? "") }))
    .sort((a, b) => b.score - a.score);
}
