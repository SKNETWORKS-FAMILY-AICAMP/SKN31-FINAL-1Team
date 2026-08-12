// ── WorkPilot AI — 도메인 타입 정의 ──────────────────────────────────
// 기획안(WorkPilot_AI_기획안) 6절 데이터 모델 + 7절 AIProvider 인터페이스를 그대로 구현한다.

export type TaskStatus =
  | "pending" // 아직 배정 전
  | "waiting_approval" // AI가 담당자를 추천했고 PM 승인 대기 중
  | "assigned" // 담당자 배정 완료, 착수 전
  | "active" // 진행 신호(커밋 등)가 있어 작업 중으로 판단
  | "done" // 완료
  | "delayed"; // 지연 위험 감지됨 (active와 병행 표시)

export interface Member {
  id: string;
  name: string;
  skills: string[];
  palette: number; // 0-5, 캐릭터 색상 팔레트 (pixel-agents 방식 차용)
  isLead?: boolean; // PM = Lead 캐릭터
  currentLoadHours: number; // 현재 배정된 미완료 작업 총 시간(부하)
  pastPerformance: Record<string, number>; // 카테고리별 과거 수행 속도/품질 점수(0~1)
}

export interface RequestAnalysis {
  rawText: string;
  included: string[]; // 포함 기능
  uncertain: string[]; // 확인 필요
  excluded: string[]; // 명시적 제외
  matchedKeywords: string[];
}

export interface Task {
  id: string;
  projectId: string;
  title: string;
  description: string;
  requiredSkills: string[];
  estimateHours: number;
  dependsOn: string[]; // 선행 Task id
  status: TaskStatus;
  assigneeId?: string;
  recommendation?: AssigneeRecommendation[]; // 승인 대기 중 추천 목록(최상위가 1순위)
  plannedStart?: string; // ISO
  plannedEnd?: string;
  actualStart?: string;
  actualEnd?: string;
  lastSignalAt?: string;
  createdFromMeetingNoteId?: string;
  /** 착수(active 전환) 시 AI가 실제로 생성한 결과물 파일 메타데이터. 내용은 서버 파일로 저장되고
   * /files/<projectId>/<filename> 로 서빙된다 — Task 객체 자체에는 경량 메타데이터만 둔다. */
  deliverable?: {
    filename: string;
    language?: string;
    generatedAt: string;
    /** 다른 작업이 이 작업의 결과물을 참고할 때 쓰는 한두 문장 요약(API 경로, 컴포넌트명 등). */
    summary?: string;
  };
}

export interface AssigneeRecommendation {
  memberId: string;
  score: number;
  reason: string;
}

export interface ProgressSignal {
  id: string;
  taskId: string;
  source: "manual" | "git" | "pr" | "ci";
  note?: string;
  timestamp: string;
}

export type DelayReason =
  | "estimate_exceeded" // 예상 소요시간 대비 경과 초과
  | "signal_stalled" // 연속 N일 진행 신호 없음
  | "dependency_slip"; // 선행 Task 지연으로 후행 착수 지연

export interface DelayAlert {
  id: string;
  taskId: string;
  detectedAt: string;
  reason: DelayReason;
  message: string;
  proposedAction: string;
  status: "open" | "acknowledged" | "resolved";
}

/** 회의/채팅 로그에서 뽑아낸 주제 하나 — 카카오톡 채팅 요약처럼 여러 화제를 나눠서 보여준다. */
export interface MeetingTopicSummary {
  topic: string;
  summary: string;
}

export interface MeetingNote {
  id: string;
  projectId: string;
  date: string;
  rawText: string;
  /** 전체 내용을 한두 문장으로 압축한 요약 — 카카오톡 채팅 요약의 상단 한줄 요약에 해당. */
  tldr: string;
  /** 주제별로 나눈 요약(최대 5개 정도). 화제가 명확히 안 나뉘면 "전체 논의" 하나로 들어온다. */
  topics: MeetingTopicSummary[];
  /** "이름: 발언" 형식의 채팅 로그에서 인식된 참여자 이름. 형식이 없으면 빈 배열. */
  participants: string[];
  decisions: string[];
  actionItems: string[];
  risks: string[];
}

export interface Notification {
  id: string;
  targetMemberId: string;
  type: "waiting_approval" | "delay" | "meeting" | "task_done";
  message: string;
  createdAt: string;
  readAt?: string;
}

export interface Project {
  id: string;
  name: string;
  stack: string[];
  createdAt: string;
  requestText: string;
  analysis?: RequestAnalysis;
  /** 모든 작업이 완료되면 AI가 자동으로 채워주는 "다음엔 뭘 할까" 제안. undefined = 아직 생성 전
   * (또는 아직 완료 안 됨), 빈 배열 = 생성했지만 추천할 게 없음. */
  nextStepSuggestions?: string[];
}

// ── AI 연동 인터페이스 (기획안 7.1) ─────────────────────────────────
// Domain Services / API 레이어는 이 인터페이스에만 의존한다.
// 지금은 MockAIProvider만 구현(규칙 기반). ClaudeAIProvider는 이후 API 키 연동 시 추가.

export interface ProjectContext {
  stack: string[];
  teamSkills: string[];
}

export interface TaskDraft {
  title: string;
  description: string;
  requiredSkills: string[];
  estimateHours: number;
  dependsOnTitles: string[]; // 같은 배치 내 다른 TaskDraft의 title 참조
}

export interface MeetingSummary {
  tldr: string;
  topics: MeetingTopicSummary[];
  participants: string[];
  decisions: string[];
  actionItems: string[];
  risks: string[];
}

export interface DeliverableResult {
  filename: string;
  language: string;
  content: string;
  /** 다른(후속) 작업의 생성 프롬프트에 그대로 들어가는 한두 문장 요약 — 노출한 API 경로,
   * 함수/컴포넌트 이름 등 "이걸 그대로 갖다 써도 된다"는 인터페이스 정보를 담는다. */
  summary: string;
}

/** 같은 프로젝트에서 이미 결과물이 생성된 작업의 요약 — 다음 작업 생성 시 컨텍스트로 함께 전달된다. */
export interface SiblingDeliverable {
  title: string;
  summary: string;
}

// 실 LLM 연동(ClaudeAIProvider)은 네트워크 호출이 필요하므로 전 메서드가
// Promise를 반환한다. MockAIProvider도 동일 시그니처(async)를 구현해 호출부는
// 항상 await 하나로 두 구현을 자유롭게 교체할 수 있다.
export interface AIProvider {
  analyzeRequest(input: string, context: ProjectContext): Promise<RequestAnalysis>;
  decomposeIntoTasks(analysis: RequestAnalysis): Promise<TaskDraft[]>;
  recommendAssignee(
    task: Pick<Task, "requiredSkills" | "title">,
    members: Member[]
  ): Promise<AssigneeRecommendation[]>;
  analyzeDelayRisk(
    task: Task,
    signals: ProgressSignal[],
    nowIso: string
  ): Promise<{ reason: DelayReason; message: string; proposedAction: string } | null>;
  summarizeMeeting(rawText: string): Promise<MeetingSummary>;
  /** 작업이 착수(active)될 때 호출 — 실제로 그 작업을 구현한 파일 하나를 만들어 반환한다.
   * siblingDeliverables는 같은 프로젝트에서 먼저 완료된 작업들의 요약(인터페이스 정보)이다 —
   * 이걸 참고해서 서로 연결되는 코드를 짜도록 유도한다. */
  generateDeliverable(
    task: Pick<Task, "id" | "title" | "description" | "requiredSkills">,
    project: Pick<Project, "name" | "stack">,
    siblingDeliverables: SiblingDeliverable[]
  ): Promise<DeliverableResult | null>;
  /** 프로젝트의 작업이 전부 완료됐을 때 호출 — 이어서 뭘 하면 좋을지 짧은 지시문 형태로 몇 개 제안한다. */
  suggestNextSteps(
    project: Pick<Project, "name" | "requestText" | "stack">,
    completedTasks: Pick<Task, "title" | "description">[]
  ): Promise<string[]>;
}
