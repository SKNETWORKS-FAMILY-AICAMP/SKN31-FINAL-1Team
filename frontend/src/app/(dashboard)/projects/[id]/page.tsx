"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import {
  FolderKanban, CalendarDays, Settings, Clock, CheckCircle2, PlayCircle, ShieldAlert, XCircle, Lock,
  Loader2, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import { KanbanBoard } from "@/components/layout/KanbanBoard";

type User = { id: string; name: string; email: string; role: string };
// Django TaskAssignmentSerializer 응답 그대로 — heyzzabi2 시절 Task와 필드명이 다르다
// (title -> task_title, assigneeId -> assigned_user, wbsStart/wbsEnd -> start_date/due_date).
type Task = {
  id: number; task_title: string; task_description: string | null;
  req_code: string; req_name: string;
  status: string; progress: number;
  start_date: string | null; due_date: string | null;
  assigned_user: number | null; assigned_user_name: string | null;
  reject_reason: string | null;
};
type Project = { id: string; name: string; description: string | null };

// Django TaskAssignment.Status 실제 값 — 예전 BACKLOG/DONE은 없고 REJECTED가 추가됐다.
const STATUSES = [
  { id: "PENDING_APPROVAL", label: "승인 대기", icon: ShieldAlert, color: "text-orange-400" },
  { id: "APPROVED", label: "승인됨", icon: CheckCircle2, color: "text-sky-400" },
  { id: "IN_PROGRESS", label: "진행 중", icon: PlayCircle, color: "text-amber-400" },
  { id: "COMPLETED", label: "완료", icon: CheckCircle2, color: "text-emerald-400" },
  { id: "REJECTED", label: "반려됨", icon: XCircle, color: "text-red-400" },
];

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  // 담당자 재배정/일정 조율은 PM의 권한이고, 상태·진행률은 "내 업무면 내가 갱신"이 자연스럽다.
  const canEditTask = (task: Task) => isPM || String(task.assigned_user) === String(user?.id);

  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"KANBAN" | "WBS" | "SETTINGS">("KANBAN");
  const [search, setSearch] = useState("");

  // Project Settings form
  const [settingsName, setSettingsName] = useState("");
  const [settingsDescription, setSettingsDescription] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);

  useEffect(() => {
    // TaskAssignment는 project를 직접 참조하지 않아서(req_item->req_def->spec->meeting->project
    // 체인을 탐) 백엔드가 ?project= 쿼리 파라미터로 필터링을 지원한다(tasks/views.py 참고).
    Promise.all([
      apiFetch<any>(`/api/projects/${id}/`),
      apiFetch<any[]>("/api/users/"),
      apiFetch<Task[]>(`/api/tasks/assignments/?project=${id}`),
    ]).then(([proj, allUsers, taskList]) => {
      setProject({ id: String(proj.id), name: proj.name, description: proj.description });
      setTasks(taskList);
      // 칸반의 담당자 드롭다운에는 실제로 업무를 받을 수 있는 사람만 나와야 한다 —
      // PM(is_staff)은 배정 대상이 아니고, 온보딩 전이라 이름이 비어있는 계정도 빈 옵션으로 보이니 제외한다.
      setUsers(
        allUsers
          .filter((u: any) => !u.is_staff && (u.first_name || u.last_name))
          .map((u: any) => ({
            id: String(u.id),
            name: `${u.last_name ?? ""}${u.first_name ?? ""}`.trim() || u.username,
            email: u.email,
            role: u.is_staff ? "PM" : "MEMBER",
          }))
      );
      setLoading(false);
    }).catch(e => {
      console.error(e);
      setLoading(false);
    });
  }, [id]);

  useEffect(() => {
    if (project) {
      setSettingsName(project.name);
      setSettingsDescription(project.description || "");
    }
  }, [project?.id]);

  const handleSaveSettings = async () => {
    if (!project || !settingsName.trim()) return;
    setSavingSettings(true);
    setSettingsSaved(false);
    try {
      const updated = await apiFetch<any>(`/api/projects/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ name: settingsName.trim(), description: settingsDescription }),
      });
      setProject({ ...project, name: updated.name, description: updated.description });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch (err: any) {
      alert(err.message || "저장에 실패했습니다.");
    } finally {
      setSavingSettings(false);
    }
  };

  const handleStatusChange = async (taskId: number, newStatus: string) => {
    const oldTasks = tasks;
    setTasks(tasks.map(t => t.id === taskId ? { ...t, status: newStatus } : t));
    try {
      await apiFetch(`/api/tasks/assignments/${taskId}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
    } catch (err: any) {
      setTasks(oldTasks);
      alert(err.message || "상태 변경에 실패했습니다.");
    }
  };

  const handleTaskUpdate = async (taskId: number, updates: Partial<Task>) => {
    const oldTasks = tasks;
    setTasks(tasks.map(t => t.id === taskId ? { ...t, ...updates } : t));
    try {
      await apiFetch(`/api/tasks/assignments/${taskId}/`, {
        method: "PATCH",
        body: JSON.stringify(updates),
      });
    } catch (err: any) {
      setTasks(oldTasks);
      alert(err.message || "저장에 실패했습니다.");
    }
  };

  if (loading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-20">
        <h2 className="text-2xl font-bold mb-2">프로젝트를 찾을 수 없습니다.</h2>
        <button onClick={() => router.push("/")} className="text-primary hover:underline">대시보드로 돌아가기</button>
      </div>
    );
  }

  const filteredTasks = tasks.filter(t =>
    !search || t.task_title.toLowerCase().includes(search.toLowerCase()) ||
    (t.assigned_user_name || "").toLowerCase().includes(search.toLowerCase())
  );

  const doneTasks = tasks.filter(t => t.status === "COMPLETED").length;
  const totalTasks = tasks.length;
  const progressPct = totalTasks > 0 ? Math.round((doneTasks / totalTasks) * 100) : 0;

  return (
    <div className="w-full max-w-7xl mx-auto space-y-6 pb-20 animate-in fade-in duration-500">

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <FolderKanban className="w-5 h-5 text-primary" />
            <h1 className="text-3xl font-bold tracking-tight">{project.name}</h1>
          </div>
          {project.description && <p className="text-muted-foreground">{project.description}</p>}
        </div>
        <div className="flex items-center gap-5 bg-black/5 dark:bg-white/5 px-5 py-3 rounded-2xl border border-border shadow-sm shrink-0 whitespace-nowrap">
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-muted-foreground mb-1.5 uppercase tracking-wider">진행률</span>
            <div className="flex items-center gap-3">
              <div className="w-32 h-2.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden shadow-inner">
                <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: `${progressPct}%` }} />
              </div>
              <span className="font-bold text-sm">{progressPct}%</span>
            </div>
          </div>
          <div className="w-px h-8 bg-black/10 dark:bg-white/10" />
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-muted-foreground mb-1 uppercase tracking-wider">완료 업무</span>
            <div className="font-black text-lg leading-none">{doneTasks} <span className="text-sm font-medium text-muted-foreground">/ {totalTasks}</span></div>
          </div>
        </div>
      </div>

      {/* Tabs & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-black/5 dark:border-white/10 pb-4">
        <div className="flex gap-1 bg-black/5 dark:bg-white/5 p-1 rounded-xl w-fit border border-black/5 dark:border-white/5">
          <button
            onClick={() => setActiveTab("KANBAN")}
            className={cn("px-4 py-2.5 rounded-lg text-sm font-bold flex items-center gap-2 transition-all", activeTab === "KANBAN" ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5")}
          >
            <FolderKanban className="w-4 h-4" /> 칸반 보드
          </button>
          <button
            onClick={() => setActiveTab("WBS")}
            className={cn("px-4 py-2.5 rounded-lg text-sm font-bold flex items-center gap-2 transition-all", activeTab === "WBS" ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5")}
          >
            <CalendarDays className="w-4 h-4" /> WBS (목록)
          </button>
          <button
            onClick={() => setActiveTab("SETTINGS")}
            className={cn("px-4 py-2.5 rounded-lg text-sm font-bold flex items-center gap-2 transition-all", activeTab === "SETTINGS" ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5")}
          >
            <Settings className="w-4 h-4" /> 설정
          </button>
        </div>

        <div className="relative group">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" />
          <input
            type="text"
            placeholder="업무 검색..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9 pr-4 py-2.5 bg-black/5 dark:bg-white/5 border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-transparent focus:bg-background w-48 transition-all focus:w-64"
          />
        </div>
        {/* "새 업무 추가"는 여기서 뺐다 — Django TaskAssignment는 req_item(요구사항 항목) FK가
            필수라 제목만으로 즉석 생성이 안 된다. 업무는 요구사항정의서 단계에서 자동배정
            (auto-assign)으로 만들어진다 — 요구사항 선택 UI가 생기면 이 자리에 다시 붙이면 된다. */}
      </div>

      {/* Tab Content */}
      <div className="pt-2">
        {activeTab === "KANBAN" && (
          <div className="flex">
            <KanbanBoard
              initialTasks={filteredTasks}
              members={users}
              onTaskChange={(taskId, patch) => setTasks(prev => prev.map(t => t.id === taskId ? { ...t, ...patch } : t))}
            />
          </div>
        )}

        {activeTab === "WBS" && (
          <div className="glass rounded-xl border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm whitespace-nowrap">
                <thead className="bg-black/10 dark:bg-white/5 text-muted-foreground text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3 font-semibold">업무명</th>
                    <th className="px-4 py-3 font-semibold">상태</th>
                    <th className="px-4 py-3 font-semibold">담당자</th>
                    <th className="px-4 py-3 font-semibold">시작일</th>
                    <th className="px-4 py-3 font-semibold">종료일</th>
                    <th className="px-4 py-3 font-semibold">진행률</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredTasks.map(task => {
                    const statusMeta = STATUSES.find(s => s.id === task.status);
                    const SIcon = statusMeta?.icon || Clock;
                    // 승인대기/반려는 칸반의 승인·반려 버튼으로만 바뀐다 — 여기 드롭다운으로는 못 바꾼다.
                    const statusLocked = task.status === "PENDING_APPROVAL" || task.status === "REJECTED" || !canEditTask(task);
                    return (
                      <tr key={task.id} className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors group">
                        <td className="px-4 py-3 font-medium min-w-[200px]">{task.task_title}</td>
                        <td className="px-4 py-3">
                          {statusLocked ? (
                            <span className={cn("inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded border", statusMeta?.color, "border-orange-400/30")}>
                              <SIcon className="w-3.5 h-3.5" /> {statusMeta?.label}
                            </span>
                          ) : (
                            <select
                              value={task.status}
                              onChange={e => handleStatusChange(task.id, e.target.value)}
                              className={cn(
                                "appearance-none bg-transparent border rounded px-2 py-1 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer",
                                statusMeta?.color.replace("text-", "border-").replace("400", "400/30"),
                                statusMeta?.color
                              )}
                            >
                              {STATUSES.filter(s => s.id === "APPROVED" || s.id === "IN_PROGRESS" || s.id === "COMPLETED").map(s => <option key={s.id} value={s.id} className="text-foreground">{s.label}</option>)}
                            </select>
                          )}
                        </td>
                        {/* 담당자 재배정은 PM의 권한 — 일반 유저는 자기 업무든 남의 업무든 여기서 담당자를 바꿀 수 없다 */}
                        <td className="px-4 py-3">
                          {isPM ? (
                            <select
                              value={task.assigned_user ? String(task.assigned_user) : ""}
                              onChange={e => handleTaskUpdate(task.id, { assigned_user: e.target.value ? Number(e.target.value) : null })}
                              className="bg-transparent border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded px-1 py-1 text-xs focus:outline-none"
                            >
                              <option value="">담당자 없음</option>
                              {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                            </select>
                          ) : (
                            <span title="담당자 재배정은 PM만 할 수 있습니다" className="inline-flex items-center gap-1 px-1 py-1 text-xs text-muted-foreground">
                              <Lock className="w-3 h-3 opacity-50" /> {task.assigned_user_name || "담당자 없음"}
                            </span>
                          )}
                        </td>
                        {/* 일정(시작/종료일) 조율도 PM의 권한 */}
                        <td className="px-4 py-3">
                          {isPM ? (
                            <input
                              type="date"
                              value={task.start_date ? task.start_date.slice(0, 10) : ""}
                              onChange={e => handleTaskUpdate(task.id, { start_date: e.target.value || null })}
                              className="bg-transparent border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded px-1 py-1 text-xs focus:outline-none text-muted-foreground"
                            />
                          ) : (
                            <span title="일정 조율은 PM만 할 수 있습니다" className="inline-flex items-center gap-1 px-1 py-1 text-xs text-muted-foreground">
                              <Lock className="w-3 h-3 opacity-50" /> {task.start_date ? task.start_date.slice(0, 10) : "-"}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {isPM ? (
                            <input
                              type="date"
                              value={task.due_date ? task.due_date.slice(0, 10) : ""}
                              onChange={e => handleTaskUpdate(task.id, { due_date: e.target.value || null })}
                              className="bg-transparent border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded px-1 py-1 text-xs focus:outline-none text-muted-foreground"
                            />
                          ) : (
                            <span title="일정 조율은 PM만 할 수 있습니다" className="inline-flex items-center gap-1 px-1 py-1 text-xs text-muted-foreground">
                              <Lock className="w-3 h-3 opacity-50" /> {task.due_date ? task.due_date.slice(0, 10) : "-"}
                            </span>
                          )}
                        </td>
                        {/* 진행률은 "내 업무"일 때만(+PM은 전체) 움직일 수 있다 */}
                        <td className="px-4 py-3">
                          {canEditTask(task) ? (
                            <div className="flex items-center gap-2 group-hover:opacity-100">
                              <input
                                type="range"
                                min="0" max="100" step="5"
                                value={task.progress || 0}
                                onChange={e => handleTaskUpdate(task.id, { progress: parseInt(e.target.value) })}
                                className="w-24 accent-primary"
                              />
                              <span className="text-xs w-8 text-right text-muted-foreground">{task.progress || 0}%</span>
                            </div>
                          ) : (
                            <div title="본인이 담당한 업무만 진행률을 바꿀 수 있습니다" className="flex items-center gap-2">
                              <Lock className="w-3 h-3 opacity-50 text-muted-foreground shrink-0" />
                              <div className="w-24 h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden">
                                <div className="h-full bg-muted-foreground/50 rounded-full" style={{ width: `${task.progress || 0}%` }} />
                              </div>
                              <span className="text-xs w-8 text-right text-muted-foreground">{task.progress || 0}%</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {filteredTasks.length === 0 && (
                    <tr><td colSpan={6} className="text-center py-12 text-muted-foreground">업무가 없습니다.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "SETTINGS" && (
          <div className="glass p-8 rounded-xl border border-border">
            <h2 className="text-xl font-bold mb-6">프로젝트 설정</h2>
            <div className="max-w-md space-y-4">
              <div>
                <label className="text-sm font-semibold mb-1 block text-muted-foreground">프로젝트명</label>
                <input
                  type="text"
                  value={settingsName}
                  onChange={e => setSettingsName(e.target.value)}
                  readOnly={!isPM}
                  className={cn(
                    "w-full px-4 py-2 bg-black/5 dark:bg-white/5 border border-border rounded-lg text-sm",
                    isPM && "focus:outline-none focus:ring-2 focus:ring-primary/40"
                  )}
                />
              </div>
              <div>
                <label className="text-sm font-semibold mb-1 block text-muted-foreground">설명</label>
                <textarea
                  value={settingsDescription}
                  onChange={e => setSettingsDescription(e.target.value)}
                  readOnly={!isPM}
                  rows={3}
                  className={cn(
                    "w-full px-4 py-2 bg-black/5 dark:bg-white/5 border border-border rounded-lg text-sm",
                    isPM && "focus:outline-none focus:ring-2 focus:ring-primary/40"
                  )}
                />
              </div>
              {isPM ? (
                <button
                  onClick={handleSaveSettings}
                  disabled={savingSettings || !settingsName.trim()}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50"
                >
                  {savingSettings ? <Loader2 className="w-4 h-4 animate-spin" /> : settingsSaved ? <CheckCircle2 className="w-4 h-4" /> : null}
                  {settingsSaved ? "저장됨" : "저장하기"}
                </button>
              ) : (
                <p className="text-xs text-muted-foreground">* 프로젝트 설정 수정은 PM만 가능합니다.</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
