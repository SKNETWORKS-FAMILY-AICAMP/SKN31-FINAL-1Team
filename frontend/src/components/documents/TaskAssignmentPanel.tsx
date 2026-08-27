"use client";

import { Fragment, useEffect, useState } from "react";
import { Bot, Loader2, ChevronDown, UserIcon, CalendarIcon, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentBadge } from "@/components/ui/AgentBadge";

type Task = {
  id: string;
  title: string;
  description: string | null;
  estimatedHours: number | null;
  status: string;
  assigneeId: string | null;
  assignee: { id: string; name: string } | null;
  wbsStart: string | null;
  wbsEnd: string | null;
  assignmentReason: string | null;
};

type Member = { id: string; name: string };

type Suggestion = {
  taskId: string;
  title: string;
  estimatedHours: number | null;
  suggestedAssigneeId: string | null;
  fitScore: number | null;
  techFit: string | null;
  workloadFit: string | null;
  experienceFit: string | null;
  suggestedWbsStart: string | null;
  suggestedWbsEnd: string | null;
};

// 편집 중인 행 하나 — 제안값에서 시작하되 PM이 담당자/일정을 직접 바꿀 수 있다
type DraftRow = {
  taskId: string;
  title: string;
  estimatedHours: number | null;
  assigneeId: string;
  fitScore: number | null;
  techFit: string | null;
  workloadFit: string | null;
  experienceFit: string | null;
  wbsStart: string; // yyyy-mm-dd for <input type="date">
  wbsEnd: string;
};

type GanttItem = { id: string; title: string; assigneeName: string; wbsStart: string; wbsEnd: string };

const toDateInput = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

// 다른 화면(업무관리 등)은 전부 한글 라벨을 쓰는데 이 표만 status 원문(IN_PROGRESS 등)을
// 그대로 보여주고 있었다 — 같은 라벨로 통일한다.
const STATUS_LABEL: Record<string, string> = {
  BACKLOG: "대기", PENDING_APPROVAL: "배분승인대기", IN_PROGRESS: "진행 중", DONE: "완료", CANCELLED: "취소됨",
};

// assignmentReason은 검증 없는 자유 텍스트 컬럼이라, 이 화면이 쓴 게 아닌 값이 들어있을 가능성을 배제할 수 없다
const parseReason = (raw: string | null) => {
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
};

export function TaskAssignmentPanel({
  doc, tasks, isPM, projectId, onRefresh,
}: {
  doc: { id: string; reqSpecStatus: string };
  tasks: Task[];
  isPM: boolean;
  projectId: string;
  onRefresh: () => void;
}) {
  const [generating, setGenerating] = useState(false);
  const [drafts, setDrafts] = useState<DraftRow[] | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [candidateMeta, setCandidateMeta] = useState<Record<string, number>>({}); // userId -> currentActiveTasks
  const [confirming, setConfirming] = useState(false);
  const [reassigning, setReassigning] = useState<string | null>(null);
  const [expandedReason, setExpandedReason] = useState<string | null>(null);

  // 담당자 변경 드롭다운에 쓸 팀원 목록은 배정 실행 여부와 무관하게 항상 필요하다.
  // 온보딩 전이라 이름이 비어있는 계정은 드롭다운에 빈 옵션으로 뜨니 제외한다.
  useEffect(() => {
    fetch("/api/users").then(r => r.json()).then(json => {
      const active = (json.data ?? []).filter((u: any) => u.role === "EMPLOYEE" && u.status === "ACTIVE" && u.name?.trim());
      setMembers(active.map((u: any) => ({ id: u.id, name: u.name })));
    }).catch(() => {});
  }, []);

  if (doc.reqSpecStatus !== "APPROVED") {
    return (
      <div className="p-10 text-center text-muted-foreground text-sm">
        요구사항정의서가 승인되면 업무분배를 진행할 수 있습니다.
      </div>
    );
  }

  const runAssign = async () => {
    setGenerating(true);
    try {
      // 이 문서에서 아직 업무가 추출된 적이 없다면 먼저 추출부터 한다
      if (tasks.length === 0) {
        const res = await fetch(`/api/projects/${projectId}/documents/${doc.id}/extract-tasks`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) { alert(data.error || "업무 생성에 실패했습니다."); return; }
        onRefresh();
      }

      const res = await fetch(`/api/projects/${projectId}/documents/${doc.id}/assign-tasks`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) { alert(data.error || "배정 추천 생성에 실패했습니다."); return; }

      const meta: Record<string, number> = {};
      (data.candidates ?? []).forEach((c: any) => { meta[c.userId] = c.currentActiveTasks; });
      setCandidateMeta(meta);
      setDrafts(
        (data.suggestions as Suggestion[]).map(s => ({
          taskId: s.taskId,
          title: s.title,
          estimatedHours: s.estimatedHours,
          assigneeId: s.suggestedAssigneeId ?? "",
          fitScore: s.fitScore,
          techFit: s.techFit,
          workloadFit: s.workloadFit,
          experienceFit: s.experienceFit,
          wbsStart: toDateInput(s.suggestedWbsStart),
          wbsEnd: toDateInput(s.suggestedWbsEnd),
        }))
      );
    } catch {
      alert("네트워크 오류가 발생했습니다.");
    } finally {
      setGenerating(false);
    }
  };

  const updateDraft = (taskId: string, patch: Partial<DraftRow>) => {
    setDrafts(prev => prev?.map(d => d.taskId === taskId ? { ...d, ...patch } : d) ?? null);
  };

  const confirmAssignment = async () => {
    if (!drafts) return;
    setConfirming(true);
    try {
      await Promise.all(
        drafts.filter(d => d.assigneeId).map(d =>
          fetch(`/api/tasks/${d.taskId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              assigneeId: d.assigneeId,
              status: "IN_PROGRESS",
              wbsStart: d.wbsStart || null,
              wbsEnd: d.wbsEnd || null,
              assignmentReason: JSON.stringify({ fitScore: d.fitScore, techFit: d.techFit, workloadFit: d.workloadFit, experienceFit: d.experienceFit }),
            }),
          })
        )
      );
      setDrafts(null);
      onRefresh();
    } finally {
      setConfirming(false);
    }
  };

  // 확정된 업무의 담당자를 나중에 바꾸는 경우 — 근거는 그 담당자를 고른 이유가 아니게 되므로 함께 지운다
  const reassign = async (taskId: string, assigneeId: string) => {
    setReassigning(taskId);
    try {
      await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assigneeId: assigneeId || null, assignmentReason: null }),
      });
      onRefresh();
    } finally {
      setReassigning(null);
    }
  };

  // 리뷰 중(제안값 편집 화면)
  if (drafts) {
    const ganttItems: GanttItem[] = drafts
      .filter(d => d.assigneeId && d.wbsStart && d.wbsEnd)
      .map(d => ({ id: d.taskId, title: d.title, assigneeName: members.find(m => m.id === d.assigneeId)?.name ?? "미배정", wbsStart: d.wbsStart, wbsEnd: d.wbsEnd }));
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          AI가 추천한 담당자와 일정입니다. 필요하면 담당자·일정을 직접 바꾼 뒤 확정하세요.
        </p>
        <GanttChart items={ganttItems} />
        <div className="border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
              <tr>
                <th className="px-4 py-3 font-bold">업무명</th>
                <th className="px-4 py-3 font-bold w-40">담당자</th>
                <th className="px-4 py-3 font-bold w-24">적합도</th>
                <th className="px-4 py-3 font-bold w-64">시작~종료일</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {drafts.map(d => (
                <Fragment key={d.taskId}>
                  <tr className="align-top">
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setExpandedReason(v => v === d.taskId ? null : d.taskId)}
                        disabled={!d.techFit}
                        className="flex items-start gap-1 font-semibold hover:text-primary transition-colors text-left disabled:cursor-default disabled:hover:text-foreground"
                      >
                        {d.techFit && <ChevronDown className={cn("w-3.5 h-3.5 transition-transform shrink-0 mt-0.5", expandedReason !== d.taskId && "-rotate-90")} />}
                        <span className="min-w-0">
                          {/* 제목이 길면 배지까지 같이 줄바꿈되며 밀려서 보기 나빴다 — 제목은 한 줄로 자르고,
                              시간 배지(요구사항정의서에서 업무를 추출할 때 AI가 함께 산정한 값)는 아래로 뺀다 */}
                          <span className="block truncate">{d.title}</span>
                          <span className="flex items-center gap-1.5 mt-0.5">
                            <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-muted-foreground font-semibold">
                              {d.estimatedHours ?? "-"}h
                            </span>
                            {d.techFit && <span className="text-xs font-normal text-muted-foreground line-clamp-1">{d.techFit}</span>}
                          </span>
                        </span>
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={d.assigneeId}
                        onChange={e => updateDraft(d.taskId, { assigneeId: e.target.value })}
                        className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40"
                      >
                        <option value="" className="bg-background text-foreground">미배정</option>
                        {members.map(m => (
                          <option key={m.id} value={m.id} className="bg-background text-foreground">{m.name}{candidateMeta[m.id] != null ? ` (진행중 ${candidateMeta[m.id]}건)` : ""}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      {d.fitScore != null ? (
                        <span className="text-[11px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-full">{d.fitScore}</span>
                      ) : <span className="text-xs text-muted-foreground">-</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <input type="date" value={d.wbsStart} onChange={e => updateDraft(d.taskId, { wbsStart: e.target.value })}
                          className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40" />
                        <span className="text-muted-foreground">~</span>
                        <input type="date" value={d.wbsEnd} onChange={e => updateDraft(d.taskId, { wbsEnd: e.target.value })}
                          className="bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40" />
                      </div>
                    </td>
                  </tr>
                  {expandedReason === d.taskId && (
                    <tr className="bg-black/[0.02] dark:bg-white/[0.02]">
                      <td colSpan={4} className="px-4 pb-3 pt-0">
                        <ul className="text-xs text-muted-foreground space-y-1 pl-5">
                          <li>🛠 기술 적합도: {d.techFit ?? "-"}</li>
                          <li>📊 업무 여유도: {d.workloadFit ?? "-"}</li>
                          <li>📁 유사 경험: {d.experienceFit ?? "-"}</li>
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={() => setDrafts(null)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-sm font-bold transition-colors"
          >
            취소
          </button>
          <button
            onClick={confirmAssignment}
            disabled={confirming}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
          >
            {confirming ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            배분 확정
          </button>
        </div>
      </div>
    );
  }

  // 아직 업무가 없거나, 미배정 업무가 남아있는 경우
  const unassigned = tasks.filter(t => !t.assigneeId);
  if (tasks.length === 0 || unassigned.length > 0) {
    return (
      <div className="space-y-5">
        {tasks.length > 0 && <AssignedList tasks={tasks} members={members} isPM={isPM} expandedReason={expandedReason} setExpandedReason={setExpandedReason} reassign={reassign} reassigning={reassigning} />}
        {isPM ? (
          <div className="p-10 text-center border border-dashed border-border rounded-xl">
            <Bot className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground mb-4">
              {tasks.length === 0 ? "요구사항정의서를 바탕으로 업무를 추출하고 담당자를 배정합니다." : `미배정 업무 ${unassigned.length}건이 있습니다.`}
            </p>
            <button
              onClick={runAssign}
              disabled={generating}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50 mx-auto"
            >
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bot className="w-4 h-4" />}
              {tasks.length === 0 ? "업무 배분 시작" : "나머지 배분 추천받기"}
              <AgentBadge agent="taskAssign" />
            </button>
          </div>
        ) : (
          <div className="p-10 text-center text-muted-foreground text-sm">
            {tasks.length === 0 ? "아직 업무분배가 시작되지 않았습니다." : `미배정 업무 ${unassigned.length}건이 있습니다.`}
          </div>
        )}
      </div>
    );
  }

  // 전부 배정 완료
  return <AssignedList tasks={tasks} members={members} isPM={isPM} expandedReason={expandedReason} setExpandedReason={setExpandedReason} reassign={reassign} reassigning={reassigning} />;
}

function AssignedList({
  tasks, members, isPM, expandedReason, setExpandedReason, reassign, reassigning,
}: {
  tasks: Task[]; members: Member[]; isPM: boolean; expandedReason: string | null; setExpandedReason: (v: string | null) => void;
  reassign: (taskId: string, assigneeId: string) => void; reassigning: string | null;
}) {
  const assigned = tasks.filter(t => t.assigneeId);
  if (assigned.length === 0) return null;

  const ganttItems: GanttItem[] = assigned
    .filter(t => t.wbsStart && t.wbsEnd)
    .map(t => ({ id: t.id, title: t.title, assigneeName: t.assignee?.name ?? "미배정", wbsStart: t.wbsStart!, wbsEnd: t.wbsEnd! }));

  return (
    <div className="space-y-4">
      <GanttChart items={ganttItems} />
      <div className="border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground uppercase bg-black/5 dark:bg-white/5">
            <tr>
              <th className="px-4 py-3 font-bold">업무명 / 배정 근거</th>
              <th className="px-4 py-3 font-bold w-44">담당자</th>
              <th className="px-4 py-3 font-bold w-40">일정</th>
              <th className="px-4 py-3 font-bold w-28">상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {assigned.map(t => {
              const reason = parseReason(t.assignmentReason);
              return (
                <Fragment key={t.id}>
                  <tr className="align-top">
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setExpandedReason(expandedReason === t.id ? null : t.id)}
                        className="flex items-start gap-1 font-semibold hover:text-primary transition-colors text-left disabled:cursor-default disabled:hover:text-foreground"
                        disabled={!reason}
                      >
                        {reason && <ChevronDown className={cn("w-3.5 h-3.5 transition-transform shrink-0 mt-0.5", expandedReason !== t.id && "-rotate-90")} />}
                        <span className="min-w-0">
                          {/* 제목은 한 줄로 자르고, 시간 배지는 아래 줄로 — 안 그러면 제목이 길 때
                              배지까지 같이 줄바꿈되며 아래로 밀려 보였다 */}
                          <span className="block truncate">{t.title}</span>
                          <span className="flex items-center gap-1.5 mt-0.5">
                            <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-muted-foreground font-semibold">
                              {t.estimatedHours ?? "-"}h
                            </span>
                            {reason?.techFit ? (
                              <span className="text-xs font-normal text-muted-foreground line-clamp-1">{reason.techFit}</span>
                            ) : (
                              <span className="text-xs font-normal text-muted-foreground/60">배정 근거 없음(수동 변경됨)</span>
                            )}
                          </span>
                        </span>
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {isPM ? (
                          <select
                            value={t.assigneeId ?? ""}
                            onChange={e => reassign(t.id, e.target.value)}
                            disabled={reassigning === t.id}
                            className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50"
                          >
                            <option value="" className="bg-background text-foreground">미배정</option>
                            {members.map(m => (
                              <option key={m.id} value={m.id} className="bg-background text-foreground">{m.name}</option>
                            ))}
                          </select>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <UserIcon className="w-3.5 h-3.5 text-muted-foreground" />
                            <span className="text-xs font-medium">{t.assignee?.name ?? "미배정"}</span>
                          </div>
                        )}
                        {reason?.fitScore != null && (
                          <span className="text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded-full shrink-0">{reason.fitScore}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {/* 날짜 범위를 한 줄에 붙여 쓰면 길이에 따라 줄바꿈 지점이 들쭉날쭉해서 보기 나빴다
                          — 시작일/종료일을 항상 두 줄로 고정해서 통일한다 */}
                      {t.wbsStart && t.wbsEnd ? (
                        <span className="flex flex-col gap-0.5">
                          <span className="flex items-center gap-1"><CalendarIcon className="w-3 h-3 shrink-0" /> {new Date(t.wbsStart).toLocaleDateString()}</span>
                          <span className="pl-4">~ {new Date(t.wbsEnd).toLocaleDateString()}</span>
                        </span>
                      ) : "-"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary">{STATUS_LABEL[t.status] ?? t.status}</span>
                    </td>
                  </tr>
                  {expandedReason === t.id && reason && (
                    <tr className="bg-black/[0.02] dark:bg-white/[0.02]">
                      <td colSpan={4} className="px-4 pb-3 pt-0">
                        <ul className="text-xs text-muted-foreground space-y-1 pl-5">
                          <li>🛠 기술 적합도: {reason.techFit ?? "-"}</li>
                          <li>📊 업무 여유도: {reason.workloadFit ?? "-"}</li>
                          <li>📁 유사 경험: {reason.experienceFit ?? "-"}</li>
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// 담당자별로 업무 막대를 타임라인 위에 배치하는 가벼운 간트 차트 — 드래그로 일정을 조정하는
// 편집형 간트는 아니고, 배정 결과를 한눈에 보여주는 용도.
//
// 예전엔 전체 기간을 6등분해서 눈금을 찍었는데, 업무 기간이 짧으면(예: 이틀) 눈금 하나가
// 몇 시간 단위가 되면서 날짜만 보이는 라벨에는 같은 날짜가 여러 번 찍히는 문제가 있었다
// ("8월 24일"이 4번 나오는 식). 시간 비례가 아니라 "하루 = 한 칸"인 날짜 그리드로 바꿔서,
// 며칠짜리 프로젝트든 항상 각 날짜가 정확히 한 번씩만 나오고 칸 사이에 점선 구분선이 생기게 한다.
function GanttChart({ items }: { items: GanttItem[] }) {
  if (items.length === 0) return null;

  // 시간대 영향 없이 "그 날짜"만 비교하려고 로컬 자정으로 맞춘다
  const toLocalMidnight = (iso: string) => {
    const d = new Date(iso);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  };
  const DAY_MS = 86400000;

  const starts = items.map(i => toLocalMidnight(i.wbsStart));
  const ends = items.map(i => toLocalMidnight(i.wbsEnd));
  const rangeStartMs = Math.min(...starts);
  const rangeEndMs = Math.max(...ends);
  // rangeEndMs가 rangeStartMs보다 앞서면(예: 오염 데이터로 유일한 항목의 시작일이 종료일보다
  // 늦은 경우) dayCount가 0 이하가 되어 Array.from({length: 음수})가 RangeError를 던진다 —
  // 최소 1일짜리 그리드로 방어한다.
  const dayCount = Math.max(1, Math.round((rangeEndMs - rangeStartMs) / DAY_MS) + 1);
  const days = Array.from({ length: dayCount }, (_, i) => new Date(rangeStartMs + i * DAY_MS));
  // 정상적인 데이터라면 항상 [0, dayCount-1] 안에 들어와야 하지만, 시작일이 종료일보다
  // 늦게 저장된 오염 데이터(서버에서도 이제 막지만 과거 데이터가 남아있을 수 있음)나 서머타임
  // 등으로 하루가 정확히 24시간이 아닌 경우 반올림이 범위를 벗어날 수 있다 — days[s]/days[e]가
  // undefined가 돼 화면이 죽었던 적이 실제로 있어서(fmtDate(undefined) 크래시), 항상 유효한
  // 인덱스로 clamp한다.
  const dayIndexOf = (iso: string) => Math.min(dayCount - 1, Math.max(0, Math.round((toLocalMidnight(iso) - rangeStartMs) / DAY_MS)));
  const fmtDate = (d: Date) => d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  const fmtWeekday = (d: Date) => d.toLocaleDateString("ko-KR", { weekday: "short" });
  const todayIndex = Math.round((toLocalMidnight(new Date().toISOString()) - rangeStartMs) / DAY_MS);

  const byAssignee = new Map<string, GanttItem[]>();
  items.forEach(i => {
    if (!byAssignee.has(i.assigneeName)) byAssignee.set(i.assigneeName, []);
    byAssignee.get(i.assigneeName)!.push(i);
  });

  const rows: { label: string | null; item: GanttItem }[] = [];
  byAssignee.forEach((personItems, name) => {
    personItems.forEach((item, idx) => rows.push({ label: idx === 0 ? name : null, item }));
  });

  // 날짜 칸 하나의 최소 너비를 보장해서 기간이 길어도 칸이 안 찌그러지고 가로 스크롤되게 한다
  const dayGridStyle = { gridTemplateColumns: `repeat(${dayCount}, minmax(52px, 1fr))` };
  const dayColClass = (i: number) =>
    cn(
      "border-l border-dashed",
      i === todayIndex ? "border-primary/40" : "border-border",
      i === dayCount - 1 && "border-r border-border"
    );

  return (
    <div className="border border-border rounded-xl p-4 overflow-x-auto">
      <div style={{ minWidth: `${96 + dayCount * 52}px` }}>
        <div className="grid gap-y-2" style={{ gridTemplateColumns: `96px 1fr` }}>
          <div />
          {/* 날짜 헤더 — 하루 = 한 칸, 오늘은 강조 */}
          <div className="grid" style={dayGridStyle}>
            {days.map((d, i) => (
              <div key={i} className={cn("text-center pb-1.5", dayColClass(i))}>
                <p className={cn("text-[10px] font-semibold", i === todayIndex ? "text-primary" : "text-muted-foreground")}>{fmtDate(d)}</p>
                <p className="text-[9px] text-muted-foreground/60">{fmtWeekday(d)}</p>
              </div>
            ))}
          </div>

          {rows.map(({ label, item }) => {
            const s = dayIndexOf(item.wbsStart);
            const e = dayIndexOf(item.wbsEnd);
            const left = (s / dayCount) * 100;
            const width = ((e - s + 1) / dayCount) * 100;
            const narrow = width < 14;
            return (
              <Fragment key={item.id}>
                <p className="text-xs font-bold text-muted-foreground flex items-center gap-1 truncate pt-1">
                  {label && (<><UserIcon className="w-3 h-3 shrink-0" /><span className="truncate">{label}</span></>)}
                </p>
                <div className="relative h-6">
                  <div className="absolute inset-0 grid" style={dayGridStyle}>
                    {days.map((_, i) => <div key={i} className={dayColClass(i)} />)}
                  </div>
                  <div
                    title={`${item.title} · ${fmtDate(days[s])} ~ ${fmtDate(days[e])}`}
                    className="absolute top-0 h-full rounded-md flex items-center px-2 bg-primary/80 hover:bg-primary transition-colors overflow-hidden"
                    style={{ left: `${left}%`, width: `${width}%` }}
                  >
                    {!narrow && <span className="text-[10px] font-semibold text-primary-foreground truncate">{item.title}</span>}
                  </div>
                  {narrow && (
                    <span
                      className="absolute top-1/2 -translate-y-1/2 text-[10px] font-medium text-foreground whitespace-nowrap pointer-events-none"
                      style={{ left: `calc(${left}% + ${width}% + 6px)` }}
                    >
                      {item.title}
                    </span>
                  )}
                </div>
              </Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}
