import { MockAIProvider } from "./aiProvider.js";
import { ClaudeAIProvider } from "./aiProviderClaude.js";
import { OpenAIProvider } from "./aiProviderOpenAI.js";
import type { AIProvider } from "./types.js";

// ── 프로바이더 선택 ──────────────────────────────────────────────────
// WORKPILOT_AI_PROVIDER=claude|openai|mock 로 명시할 수 있고, 지정하지 않으면
// 설정된 API 키를 보고 자동으로 고른다(ANTHROPIC_API_KEY 우선 -> OPENAI_API_KEY -> Mock).
// 두 키가 모두 없거나, 지정한 프로바이더의 키가 없으면 각 프로바이더가 메서드 호출마다
// MockAIProvider로 조용히 폴백하므로 서버는 항상 뜬다.

export type AIProviderName = "claude" | "openai" | "mock";

export interface ActiveAIProvider {
  provider: AIProvider;
  name: AIProviderName;
  isLive: boolean;
}

export function createAIProvider(): ActiveAIProvider {
  const forced = (process.env.WORKPILOT_AI_PROVIDER ?? "").trim().toLowerCase();

  if (forced === "openai") return use(new OpenAIProvider(), "openai");
  if (forced === "claude" || forced === "anthropic") return use(new ClaudeAIProvider(), "claude");
  if (forced === "mock" || forced === "none") {
    console.log("[WorkPilot AI] using MockAIProvider (WORKPILOT_AI_PROVIDER=mock)");
    return { provider: new MockAIProvider(), name: "mock", isLive: false };
  }

  // 자동 감지: 설정된 키를 우선순위대로 사용.
  if (process.env.ANTHROPIC_API_KEY) return use(new ClaudeAIProvider(), "claude");
  if (process.env.OPENAI_API_KEY) return use(new OpenAIProvider(), "openai");

  console.log(
    "[WorkPilot AI] using MockAIProvider (rule-based) — set ANTHROPIC_API_KEY or OPENAI_API_KEY " +
      "(and optionally WORKPILOT_AI_PROVIDER) to enable real LLM judgment"
  );
  return { provider: new MockAIProvider(), name: "mock", isLive: false };
}

function use(provider: ClaudeAIProvider | OpenAIProvider, name: AIProviderName): ActiveAIProvider {
  console.log(
    `[WorkPilot AI] using ${name} provider (${provider.isLive ? "live — API key found" : "no API key found, falling back to Mock per call"})`
  );
  return { provider, name, isLive: provider.isLive };
}
