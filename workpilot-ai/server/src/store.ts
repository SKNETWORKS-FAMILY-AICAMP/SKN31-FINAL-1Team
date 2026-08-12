import type {
  DelayAlert,
  Member,
  MeetingNote,
  Notification,
  Project,
  ProgressSignal,
  Task,
} from "./types.js";

// ── 인메모리 스토어 ──────────────────────────────────────────────────
// MVP(Phase 1) 범위이므로 DB 대신 프로세스 메모리에 보관한다.
// 기획안 8절 기술 스택의 PostgreSQL 전환 시 이 모듈의 인터페이스만 유지하고
// 구현을 교체하면 된다.

let seq = 1;
export function nextId(prefix: string): string {
  return `${prefix}_${(seq++).toString(36)}${Date.now().toString(36)}`;
}

class Store {
  members = new Map<string, Member>();
  projects = new Map<string, Project>();
  tasks = new Map<string, Task>();
  signals: ProgressSignal[] = [];
  alerts = new Map<string, DelayAlert>();
  notes = new Map<string, MeetingNote>();
  notifications = new Map<string, Notification>();

  /** 데모/테스트용 가상 시계 오프셋(ms). 실제 며칠을 기다리지 않고
   * 지연 감지 로직을 검증할 수 있도록 /api/simulate/advance 로 앞당긴다. */
  clockOffsetMs = 0;

  nowIso(): string {
    return new Date(Date.now() + this.clockOffsetMs).toISOString();
  }

  tasksByProject(projectId: string): Task[] {
    return Array.from(this.tasks.values()).filter(
      (t) => t.projectId === projectId
    );
  }

  addNotification(targetMemberId: string, type: Notification["type"], message: string) {
    const n: Notification = {
      id: nextId("notif"),
      targetMemberId,
      type,
      message,
      createdAt: this.nowIso(),
    };
    this.notifications.set(n.id, n);
    return n;
  }

  reset() {
    this.projects.clear();
    this.tasks.clear();
    this.signals = [];
    this.alerts.clear();
    this.notes.clear();
    this.notifications.clear();
    this.clockOffsetMs = 0;
  }
}

export const store = new Store();

export function seedMembers() {
  const seed: Array<Omit<Member, "currentLoadHours" | "pastPerformance">> = [
    { id: "m_pm", name: "김민준(PM)", skills: ["기획", "관리"], palette: 0, isLead: true },
    { id: "m_be1", name: "박서연", skills: ["Backend", "DB"], palette: 1 },
    { id: "m_be2", name: "이도현", skills: ["Backend", "외부연동"], palette: 2 },
    { id: "m_fe1", name: "최지우", skills: ["Frontend"], palette: 3 },
    { id: "m_fe2", name: "정하은", skills: ["Frontend", "UI"], palette: 4 },
    { id: "m_qa1", name: "한소율", skills: ["Test", "QA"], palette: 5 },
  ];
  for (const m of seed) {
    store.members.set(m.id, {
      ...m,
      currentLoadHours: 0,
      pastPerformance: {
        Backend: 0.6 + Math.random() * 0.3,
        Frontend: 0.6 + Math.random() * 0.3,
        DB: 0.6 + Math.random() * 0.3,
        Test: 0.6 + Math.random() * 0.3,
        QA: 0.6 + Math.random() * 0.3,
        외부연동: 0.6 + Math.random() * 0.3,
      },
    });
  }
}
