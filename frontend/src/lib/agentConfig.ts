// 3개 AI 에이전트(기획서 생성 / 요구사항정의서 생성 / 업무 배분)의 세부 설정.
// Project.agentConfig 컬럼에 JSON 문자열로 저장된다(프로젝트 내 다른 JSON 필드들과 동일한 관례).
export type AgentConfig = {
  proposal: { temperature: number };
  reqSpec: { temperature: number };
  taskAssign: { temperature: number; minTasks: number; maxTasks: number };
};

// generate/route.ts, extract-tasks/route.ts가 원래 쓰던 하드코딩 값과 동일 — 설정 페이지를
// 아직 안 연 프로젝트(agentConfig가 null)도 기존과 완전히 같게 동작해야 한다.
export const DEFAULT_AGENT_CONFIG: AgentConfig = {
  proposal: { temperature: 0.0 },
  reqSpec: { temperature: 0.0 },
  taskAssign: { temperature: 0.1, minTasks: 3, maxTasks: 7 },
};

// 이 파이프라인은 "원본에 없는 내용은 절대 지어내지 않는다"는 환각 방지 원칙이 핵심 설계
// 기준이다(PROJECT_STATUS.md 참고). temperature를 자유롭게 올리게 두면 이 원칙이 무너지므로,
// 화면의 슬라이더 범위와 별개로 서버에서도 항상 이 범위로 clamp한다 — API를 직접 호출해도 못 벗어난다.
const TEMPERATURE_RANGE = { min: 0, max: 0.3 };
const TASK_COUNT_RANGE = { min: 1, max: 15 };

const clampTemperature = (v: unknown, fallback: number): number => {
  const n = typeof v === "number" && Number.isFinite(v) ? v : fallback;
  return Math.min(TEMPERATURE_RANGE.max, Math.max(TEMPERATURE_RANGE.min, n));
};

const clampTaskCount = (v: unknown, fallback: number): number => {
  const n = typeof v === "number" && Number.isInteger(v) ? v : fallback;
  return Math.min(TASK_COUNT_RANGE.max, Math.max(TASK_COUNT_RANGE.min, n));
};

// project.agentConfig(JSON 문자열 또는 null)를 안전하게 파싱 + clamp해서 반환한다.
// 값이 없거나(방문 전) 깨져있어도(수동 DB 조작 등) 항상 유효한 설정으로 폴백한다.
export function parseAgentConfig(raw: string | null | undefined): AgentConfig {
  let parsed: Partial<{
    proposal: Partial<AgentConfig["proposal"]>;
    reqSpec: Partial<AgentConfig["reqSpec"]>;
    taskAssign: Partial<AgentConfig["taskAssign"]>;
  }> = {};
  if (raw) {
    try { parsed = JSON.parse(raw); } catch { /* 깨진 값이면 기본값으로 폴백 */ }
  }

  const minTasks = clampTaskCount(parsed.taskAssign?.minTasks, DEFAULT_AGENT_CONFIG.taskAssign.minTasks);
  const maxTasksRaw = clampTaskCount(parsed.taskAssign?.maxTasks, DEFAULT_AGENT_CONFIG.taskAssign.maxTasks);

  return {
    proposal: { temperature: clampTemperature(parsed.proposal?.temperature, DEFAULT_AGENT_CONFIG.proposal.temperature) },
    reqSpec: { temperature: clampTemperature(parsed.reqSpec?.temperature, DEFAULT_AGENT_CONFIG.reqSpec.temperature) },
    taskAssign: {
      temperature: clampTemperature(parsed.taskAssign?.temperature, DEFAULT_AGENT_CONFIG.taskAssign.temperature),
      minTasks,
      maxTasks: Math.max(minTasks, maxTasksRaw), // max가 min보다 작아지는 저장 오류를 방어
    },
  };
}
