import { MockAIProvider } from "./aiProvider.js";
import { normalizeDrafts, normalizeRecommendations, sanitizeFilename } from "./aiProviderClaude.js";
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

// ── OpenAIProvider ───────────────────────────────────────────────────
// ClaudeAIProvider와 동일한 AIProvider 인터페이스를 OpenAI Chat Completions API로
// 구현한다. SDK 없이 fetch만 사용. response_format=json_object를 쓰므로 응답은
// 항상 최상위가 객체여야 해서, 배열이 필요한 decompose/recommend는 {"tasks":[...]},
// {"recommendations":[...]} 형태로 감싸서 받고 여기서 풀어낸다.
//
// analyzeDelayRisk는 ClaudeAIProvider와 동일하게 순수 날짜 계산이라 LLM을 부르지 않는다.
// 모든 메서드는 실패 시 MockAIProvider로 조용히 폴백한다.

const OPENAI_API_URL = "https://api.openai.com/v1/chat/completions";

let loggedMissingKey = false;

export class OpenAIProvider implements AIProvider {
  readonly kind = "openai" as const;
  private fallback = new MockAIProvider();
  private apiKey: string | undefined;
  private model: string;

  constructor(opts?: { apiKey?: string; model?: string }) {
    this.apiKey = opts?.apiKey ?? process.env.OPENAI_API_KEY;
    this.model = opts?.model ?? process.env.WORKPILOT_OPENAI_MODEL ?? process.env.WORKPILOT_AI_MODEL ?? "gpt-4o-mini";
  }

  get isLive(): boolean {
    return Boolean(this.apiKey);
  }

  private async callJson<T>(system: string, user: string, maxTokens = 1500): Promise<T | null> {
    if (!this.apiKey) {
      if (!loggedMissingKey) {
        console.warn("[WorkPilot AI] OPENAI_API_KEY not set — OpenAIProvider falling back to MockAIProvider per call.");
        loggedMissingKey = true;
      }
      return null;
    }
    try {
      const res = await fetch(OPENAI_API_URL, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify({
          model: this.model,
          max_tokens: maxTokens,
          temperature: 0.3,
          response_format: { type: "json_object" },
          messages: [
            { role: "system", content: system },
            { role: "user", content: user },
          ],
        }),
      });
      if (!res.ok) {
        console.error(`[WorkPilot AI] OpenAI API error ${res.status}: ${await res.text().catch(() => "")}`);
        return null;
      }
      const data = (await res.json()) as { choices?: Array<{ message?: { content?: string } }> };
      const text = data.choices?.[0]?.message?.content;
      if (!text) return null;
      return parseJsonLoose<T>(text);
    } catch (err) {
      console.error("[WorkPilot AI] OpenAI API call failed:", err);
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
        "추려냅니다. 반드시 JSON 객체만 출력하세요. 스키마: " +
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
    const result = await this.callJson<{ tasks: TaskDraft[] }>(
      "당신은 소프트웨어 프로젝트를 WBS(작업 분해 구조)로 쪼개는 테크리드입니다. " +
        "요청 분석 결과를 받아 실행 가능한 작업 목록으로 분해하세요. 각 작업은 " +
        "title(간결한 한국어), description, requiredSkills(Backend/Frontend/DB/Test/QA/외부연동/기획 중에서), " +
        "estimateHours(현실적인 작업시간, 정수), dependsOnTitles(같은 목록 내 선행 작업의 title 배열, 없으면 빈 배열)를 " +
        `가집니다. 반드시 JSON 객체만 출력하세요. 스키마: {"tasks": [{"title": string, "description": string, ` +
        `"requiredSkills": string[], "estimateHours": number, "dependsOnTitles": string[]}]}`,
      `포함 기능: ${analysis.included.join(", ") || "(원문 참고)"}\n` +
        `확인 필요 사항: ${analysis.uncertain.join(", ") || "없음"}\n` +
        `원문 요청: "${analysis.rawText}"`,
      2000
    );
    if (!result || !Array.isArray(result.tasks) || result.tasks.length === 0) {
      return this.fallback.decomposeIntoTasks(analysis);
    }
    return normalizeDrafts(result.tasks);
  }

  async recommendAssignee(
    task: Pick<Task, "requiredSkills" | "title">,
    members: Member[]
  ): Promise<AssigneeRecommendation[]> {
    const candidates = members.filter((m) => !m.isLead);
    const pool = candidates.length > 0 ? candidates : members;
    const result = await this.callJson<{ recommendations: AssigneeRecommendation[] }>(
      "당신은 팀원의 스킬/현재 부하/과거 성과를 근거로 작업 담당자를 추천하는 배정 어시스턴트입니다. " +
        "각 후보에 대해 0~1 사이 score와, 왜 그 점수인지 한국어로 짧게 설명하는 reason을 만드세요. " +
        `score가 높은 순으로 정렬해서, 반드시 JSON 객체만 출력하세요. 스키마: ` +
        `{"recommendations": [{"memberId": string, "score": number, "reason": string}]}`,
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
    return normalizeRecommendations(result?.recommendations ?? null, pool) ?? this.fallback.recommendAssignee(task, members);
  }

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
        "반드시 JSON 객체만 출력하세요. 스키마: " +
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
        "리스크/이슈(risks)를 뽑아내세요. 반드시 JSON 객체만 출력하세요. 스키마: " +
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
