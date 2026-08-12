import type { Member, Task } from "../types.js";
import {
  drawActivityLabel,
  drawBookshelf,
  drawCharacter,
  drawDesk,
  drawPlant,
  drawSpeechBubble,
  preloadCharacterSprites,
} from "./sprites.js";
import type { BubbleKind, CharState } from "./sprites.js";

interface Seat {
  memberId: string;
  x: number;
  y: number;
}

interface MemberState {
  charState: CharState;
  taskTitle?: string;
}

const FLOOR_A = "#2a2740";
const FLOOR_B = "#252238";
const FLOOR_SEAM = "rgba(0,0,0,0.15)";

export class OfficeCanvas {
  private ctx: CanvasRenderingContext2D;
  private seats: Seat[] = [];
  private memberStates = new Map<string, MemberState>();
  private members: Member[] = [];
  private prevTaskStatus = new Map<string, string>();
  private transientBubbles = new Map<string, { kind: BubbleKind; expiresAt: number }>(); // memberId -> bubble
  private t0 = performance.now();
  private raf = 0;

  constructor(private canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D context unavailable");
    this.ctx = ctx;
    preloadCharacterSprites();
    this.resize();
    window.addEventListener("resize", () => this.resize());
  }

  private resize() {
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.round(rect.width * dpr);
    this.canvas.height = Math.round(rect.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.layoutSeats();
  }

  private layoutSeats() {
    const rect = this.canvas.getBoundingClientRect();
    const w = rect.width;
    const lead = this.members.find((m) => m.isLead);
    const others = this.members.filter((m) => !m.isLead);

    const seats: Seat[] = [];
    if (lead) seats.push({ memberId: lead.id, x: w / 2, y: 110 });

    const cols = Math.max(1, Math.min(4, others.length));
    const gapX = Math.min(160, (w - 80) / cols);
    const startX = w / 2 - (gapX * (cols - 1)) / 2;
    others.forEach((m, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      seats.push({
        memberId: m.id,
        x: startX + col * gapX,
        y: 240 + row * 140,
      });
    });
    this.seats = seats;
  }

  setState(members: Member[], tasks: Task[]) {
    this.members = members;
    this.layoutSeats();

    // 완료 전이 감지 -> 2초 체크마크 말풍선
    for (const t of tasks) {
      const prev = this.prevTaskStatus.get(t.id);
      if (prev && prev !== "done" && t.status === "done" && t.assigneeId) {
        this.transientBubbles.set(t.assigneeId, {
          kind: "done",
          expiresAt: performance.now() + 2000,
        });
      }
      this.prevTaskStatus.set(t.id, t.status);
    }

    const states = new Map<string, MemberState>();
    for (const m of members) {
      if (m.isLead) {
        const pendingApprovals = tasks.filter((t) => t.status === "waiting_approval").length;
        states.set(m.id, {
          charState: pendingApprovals > 0 ? "waiting_approval" : "idle",
          taskTitle: pendingApprovals > 0 ? `승인 대기 ${pendingApprovals}건` : undefined,
        });
        continue;
      }
      const myTasks = tasks.filter((t) => t.assigneeId === m.id);
      const delayed = myTasks.find((t) => t.status === "delayed");
      const active = myTasks.find((t) => t.status === "active");
      const waitingRecommendedFor = tasks.find(
        (t) => t.status === "waiting_approval" && t.recommendation?.[0]?.memberId === m.id
      );

      if (delayed) states.set(m.id, { charState: "delayed", taskTitle: delayed.title });
      else if (active) states.set(m.id, { charState: "active", taskTitle: active.title });
      else if (waitingRecommendedFor)
        states.set(m.id, { charState: "waiting_approval", taskTitle: waitingRecommendedFor.title });
      else states.set(m.id, { charState: "idle" });
    }
    this.memberStates = states;
  }

  start() {
    const loop = () => {
      this.render();
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop() {
    cancelAnimationFrame(this.raf);
  }

  private render() {
    const rect = this.canvas.getBoundingClientRect();
    const { ctx } = this;
    const w = rect.width;
    const h = rect.height;
    const bob = (performance.now() - this.t0) / 1000;

    this.drawFloor(w, h);
    this.drawRoomDecor(w, h);

    // z-정렬: y가 작은(위쪽) 좌석부터 그려야 아래쪽 캐릭터가 위쪽 책상을 가리지 않는다.
    const orderedSeats = [...this.seats].sort((a, b) => a.y - b.y);

    for (const seat of orderedSeats) {
      const member = this.members.find((m) => m.id === seat.memberId);
      if (!member) continue;
      const st = this.memberStates.get(seat.memberId) ?? { charState: "idle" as CharState };
      const seed = member.palette + seat.memberId.length;

      drawDesk(ctx, { x: seat.x, y: seat.y + 8, state: st.charState, seed, glowPhase: bob });

      drawCharacter(ctx, {
        x: seat.x,
        y: seat.y,
        palette: member.palette,
        isLead: member.isLead,
        state: st.charState,
        bobPhase: bob + seat.x * 0.01,
      });

      // 이름표
      ctx.save();
      ctx.font = "11px monospace";
      ctx.fillStyle = "#e8e8f0";
      ctx.textAlign = "center";
      ctx.fillText(member.name, seat.x, seat.y + 46);
      ctx.restore();

      // 활동 라벨: 지금 하고 있는 작업명 (idle이면 표시하지 않음)
      if (st.taskTitle && st.charState !== "idle") {
        drawActivityLabel(ctx, seat.x, seat.y - 46, st.taskTitle, st.charState);
      }

      // 말풍선 우선순위: 지연 > 승인대기 > 완료(임시)
      const transient = this.transientBubbles.get(seat.memberId);
      if (transient && transient.expiresAt < performance.now()) {
        this.transientBubbles.delete(seat.memberId);
      }
      let bubbleKind: BubbleKind | null = null;
      if (st.charState === "delayed") bubbleKind = "delay";
      else if (st.charState === "waiting_approval") bubbleKind = "waiting";
      else if (transient) bubbleKind = transient.kind;

      if (bubbleKind) {
        drawSpeechBubble(ctx, seat.x, seat.y - 34, bubbleKind);
      }
    }

    if (this.members.length === 0) {
      ctx.fillStyle = "#8888a0";
      ctx.font = "14px monospace";
      ctx.textAlign = "center";
      ctx.fillText("업무를 요청하면 팀이 사무실에 나타납니다", w / 2, h / 2);
    }
  }

  private drawFloor(w: number, h: number) {
    const { ctx } = this;
    const TILE = 32;
    for (let y = 0; y < h; y += TILE) {
      for (let x = 0; x < w; x += TILE) {
        const idx = (Math.floor(x / TILE) + Math.floor(y / TILE)) % 2;
        ctx.fillStyle = idx === 0 ? FLOOR_A : FLOOR_B;
        ctx.fillRect(x, y, TILE, TILE);
      }
      ctx.strokeStyle = FLOOR_SEAM;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, y + TILE);
      ctx.lineTo(w, y + TILE);
      ctx.stroke();
    }
    // 은은한 상단 비네트로 깊이감
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, "rgba(0,0,0,0.28)");
    grad.addColorStop(0.15, "rgba(0,0,0,0)");
    grad.addColorStop(1, "rgba(0,0,0,0.05)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
  }

  private drawRoomDecor(w: number, _h: number) {
    const { ctx } = this;
    // 위쪽 벽 라인 + 책장
    ctx.fillStyle = "#1b1a29";
    ctx.fillRect(0, 0, w, 26);
    ctx.strokeStyle = "rgba(0,0,0,0.4)";
    ctx.beginPath();
    ctx.moveTo(0, 26);
    ctx.lineTo(w, 26);
    ctx.stroke();

    if (w > 260) {
      drawBookshelf(ctx, 56, 70);
      drawBookshelf(ctx, w - 56, 70);
    }
    drawPlant(ctx, 30, 96, 0.9);
    if (w > 200) drawPlant(ctx, w - 30, 96, 0.9);
  }
}
