// 서버 도메인 타입의 클라이언트측 미러 (server/src/types.ts 참고).
// 별도 프로젝트 경계이므로 타입을 공유 패키지로 묶지 않고 필요한 만큼만 복제한다.

export type TaskStatus =
  | "pending"
  | "waiting_approval"
  | "assigned"
  | "active"
  | "done"
  | "delayed";

export interface Member {
  id: string;
  name: string;
  skills: string[];
  palette: number;
  isLead?: boolean;
  currentLoadHours: number;
  pastPerformance: Record<string, number>;
}

export interface AssigneeRecommendation {
  memberId: string;
  score: number;
  reason: string;
}

export interface Task {
  id: string;
  projectId: string;
  title: string;
  description: string;
  requiredSkills: string[];
  estimateHours: number;
  dependsOn: string[];
  status: TaskStatus;
  assigneeId?: string;
  recommendation?: AssigneeRecommendation[];
  plannedStart?: string;
  plannedEnd?: string;
  actualStart?: string;
  actualEnd?: string;
  lastSignalAt?: string;
  createdFromMeetingNoteId?: string;
  deliverable?: {
    filename: string;
    language?: string;
    generatedAt: string;
    summary?: string;
  };
}

export interface DelayAlert {
  id: string;
  taskId: string;
  detectedAt: string;
  reason: "estimate_exceeded" | "signal_stalled" | "dependency_slip";
  message: string;
  proposedAction: string;
  status: "open" | "acknowledged" | "resolved";
}

export interface MeetingTopicSummary {
  topic: string;
  summary: string;
}

/** 회의 요약에 첨부하는 파일 — 브라우저에서 base64로 인코딩해 그대로 JSON에 실어 보낸다
 * (별도 업로드 엔드포인트/멀티파트 파서 없이 기존 JSON API를 재사용하기 위함). */
export interface MeetingAttachmentPayload {
  name: string;
  mimeType: string;
  dataBase64: string;
}

export interface MeetingNote {
  id: string;
  projectId: string;
  date: string;
  rawText: string;
  tldr: string;
  topics: MeetingTopicSummary[];
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

export interface RequestAnalysis {
  rawText: string;
  included: string[];
  uncertain: string[];
  excluded: string[];
  matchedKeywords: string[];
}

export interface Project {
  id: string;
  name: string;
  stack: string[];
  createdAt: string;
  requestText: string;
  analysis?: RequestAnalysis;
  nextStepSuggestions?: string[];
}

export interface ProjectState {
  project: Project;
  tasks: Task[];
  members: Member[];
  alerts: DelayAlert[];
  meetingNotes: MeetingNote[];
  notifications: Notification[];
  now: string;
}
