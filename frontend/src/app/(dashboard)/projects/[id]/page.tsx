"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import {
  FolderKanban, CalendarDays, Settings, Plus, MoreHorizontal,
  Clock, CheckCircle2, PlayCircle, ShieldAlert, Lock,
  Loader2, Search, ArrowRight, User as UserIcon, CalendarIcon
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { KanbanBoard } from "@/components/layout/KanbanBoard";

type User = { id: string; name: string; email: string; role: string };
type Task = {
  id: string; title: string; description: string | null;
  status: string; progress: number;
  wbsStart: string | null; wbsEnd: string | null;
  assigneeId: string | null;
  assignee: { id: string; name: string; email: string } | null;
  createdAt: string;
};
type Project = {
  id: string; name: string; description: string | null;
  startDate: string | null; endDate: string | null;
  tasks: Task[];
};

const STATUSES = [
  { id: "BACKLOG", label: "대기", icon: Clock, color: "text-gray-400" },
  { id: "PENDING_APPROVAL", label: "배분승인대기", icon: ShieldAlert, color: "text-orange-400" },
  { id: "IN_PROGRESS", label: "진행 중", icon: PlayCircle, color: "text-amber-400" },
  { id: "DONE", label: "완료", icon: CheckCircle2, color: "text-emerald-400" }
];

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  // 담당자 재배정/일정 조율은 PM의 권한이고, 상태·진행률은 "내 업무면 내가 갱신"이 자연스럽다.
  // 지금까지는 이 화면에 아무 권한 구분이 없어서 일반 유저가 남의 업무 진행률까지 바꿀 수 있었다.
  const canEditTask = (task: Task) => isPM || task.assigneeId === user?.id;

  const [project, setProject] = useState<Project | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"KANBAN" | "WBS" | "SETTINGS">("KANBAN");
  const [search, setSearch] = useState("");

  // Project Settings form
  const [settingsName, setSettingsName] = useState("");
  const [settingsDescription, setSettingsDescription] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);

  // Add Task Modal
  const [addModal, setAddModal] = useState(false);
  const [newTask, setNewTask] = useState({ title: "", description: "", assigneeId: "", wbsStart: "", wbsEnd: "" });
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`/api/projects/${id}`).then(r => r.json()),
      fetch(`/api/users`).then(r => r.json())
    ]).then(([projRes, usersRes]) => {
      if (projRes.success) setProject(projRes.data);
      // 칸반의 담당자 드롭다운에는 실제로 업무를 받을 수 있는 사람만 나와야 한다 —
      // PM은 배정 대상이 아니고, 온보딩 전이라 이름이 비어있는 계정도 빈 옵션으로 보이니 제외한다.
      if (usersRes.success) setUsers(usersRes.data.filter((u: User) => u.role !== "PM" && u.name?.trim()));
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
      const res = await fetch(`/api/projects/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: settingsName.trim(), description: settingsDescription }),
      });
      const data = await res.json();
      if (data.success) {
        setProject({ ...project, name: data.data.name, description: data.data.description });
        setSettingsSaved(true);
        setTimeout(() => setSettingsSaved(false), 2000);
      }
    } finally {
      setSavingSettings(false);
    }
  };

  const handleStatusChange = async (taskId: string, newStatus: string) => {
    if (!project) return;
    // Optimistic UI
    const oldTasks = [...project.tasks];
    setProject({
      ...project,
      tasks: project.tasks.map(t => t.id === taskId ? { ...t, status: newStatus } : t)
    });

    try {
      const res = await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus })
      });
      if (!res.ok) throw new Error("Failed");
    } catch {
      setProject({ ...project, tasks: oldTasks });
    }
  };

  const handleTaskUpdate = async (taskId: string, updates: Partial<Task>) => {
    if (!project) return;
    const oldTasks = [...project.tasks];
    setProject({
      ...project,
      tasks: project.tasks.map(t => t.id === taskId ? { ...t, ...updates } : t)
    });

    try {
      await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates)
      });
    } catch {
      setProject({ ...project, tasks: oldTasks });
    }
  };

  const handleAddTask = async () => {
    if (!newTask.title.trim() || !project) return;
    setAdding(true);
    
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: id,
          title: newTask.title,
          description: newTask.description,
          assigneeId: newTask.assigneeId || null,
          wbsStart: newTask.wbsStart || null,
          wbsEnd: newTask.wbsEnd || null,
          status: "BACKLOG"
        })
      });
      const data = await res.json();
      if (res.ok) {
        // Find assignee details if set
        const assignee = users.find(u => u.id === data.assigneeId) || null;
        setProject({ ...project, tasks: [{ ...data, assignee }, ...project.tasks] });
        setAddModal(false);
        setNewTask({ title: "", description: "", assigneeId: "", wbsStart: "", wbsEnd: "" });
      }
    } finally {
      setAdding(false);
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

  const filteredTasks = project.tasks.filter(t => 
    !search || t.title.toLowerCase().includes(search.toLowerCase()) || 
    (t.assignee?.name || "").toLowerCase().includes(search.toLowerCase())
  );

  const doneTasks = project.tasks.filter(t => t.status === "DONE").length;
  const totalTasks = project.tasks.length;
  const progressPct = totalTasks > 0 ? Math.round((doneTasks / totalTasks) * 100) : 0;

  return (
    <div className="w-full max-w-7xl mx-auto space-y-6 pb-20 animate-in fade-in duration-500">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        {/* min-w-0이 없으면 옆의 통계 박스가 flex의 기본 shrink 동작 때문에 밀려서 찌그러지고,
            그 안의 "완료 업무" 같은 한글 텍스트가 글자 단위로 세로 줄바꿈되는 문제가 있었다. */}
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

        <div className="flex items-center gap-3">
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
          <button
            onClick={() => setAddModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-bold shadow-md hover:bg-primary/90 hover:shadow-lg transition-all active:scale-95"
          >
            <Plus className="w-4 h-4" /> 새 업무
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="pt-2">
        {activeTab === "KANBAN" && (
          <div className="flex">
            <KanbanBoard projectId={id} initialTasks={filteredTasks} members={users} />
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
                    return (
                      <tr key={task.id} className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors group">
                        <td className="px-4 py-3 font-medium min-w-[200px]">{task.title}</td>
                        <td className="px-4 py-3">
                          {task.status === "PENDING_APPROVAL" || !canEditTask(task) ? (
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
                              {STATUSES.filter(s => s.id !== "PENDING_APPROVAL").map(s => <option key={s.id} value={s.id} className="text-foreground">{s.label}</option>)}
                            </select>
                          )}
                        </td>
                        {/* 담당자 재배정은 PM의 권한 — 일반 유저는 자기 업무든 남의 업무든 여기서 담당자를 바꿀 수 없다 */}
                        <td className="px-4 py-3">
                          {isPM ? (
                            <select
                              value={task.assigneeId || ""}
                              onChange={e => handleTaskUpdate(task.id, { assigneeId: e.target.value || null })}
                              className="bg-transparent border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded px-1 py-1 text-xs focus:outline-none"
                            >
                              <option value="">담당자 없음</option>
                              {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                            </select>
                          ) : (
                            <span title="담당자 재배정은 PM만 할 수 있습니다" className="inline-flex items-center gap-1 px-1 py-1 text-xs text-muted-foreground">
                              <Lock className="w-3 h-3 opacity-50" /> {task.assignee?.name || "담당자 없음"}
                            </span>
                          )}
                        </td>
                        {/* 일정(WBS 시작/종료일) 조율도 PM의 권한 */}
                        <td className="px-4 py-3">
                          {isPM ? (
                            <input
                              type="date"
                              value={task.wbsStart ? new Date(task.wbsStart).toISOString().split('T')[0] : ""}
                              onChange={e => handleTaskUpdate(task.id, { wbsStart: e.target.value ? new Date(e.target.value).toISOString() : null })}
                              className="bg-transparent border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded px-1 py-1 text-xs focus:outline-none text-muted-foreground"
                            />
                          ) : (
                            <span title="일정 조율은 PM만 할 수 있습니다" className="inline-flex items-center gap-1 px-1 py-1 text-xs text-muted-foreground">
                              <Lock className="w-3 h-3 opacity-50" /> {task.wbsStart ? new Date(task.wbsStart).toISOString().split('T')[0] : "-"}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {isPM ? (
                            <input
                              type="date"
                              value={task.wbsEnd ? new Date(task.wbsEnd).toISOString().split('T')[0] : ""}
                              onChange={e => handleTaskUpdate(task.id, { wbsEnd: e.target.value ? new Date(e.target.value).toISOString() : null })}
                              className="bg-transparent border border-transparent hover:border-black/10 dark:hover:border-white/10 rounded px-1 py-1 text-xs focus:outline-none text-muted-foreground"
                            />
                          ) : (
                            <span title="일정 조율은 PM만 할 수 있습니다" className="inline-flex items-center gap-1 px-1 py-1 text-xs text-muted-foreground">
                              <Lock className="w-3 h-3 opacity-50" /> {task.wbsEnd ? new Date(task.wbsEnd).toISOString().split('T')[0] : "-"}
                            </span>
                          )}
                        </td>
                        {/* 진행률은 "내 업무"일 때만(+PM은 전체) 움직일 수 있다 — 예전엔 아무나 남의 업무
                            진행률까지 바꿀 수 있었다(사용자가 실제로 발견한 버그) */}
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

      {/* Add Task Modal */}
      {addModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-md w-full mx-4">
            <h3 className="text-xl font-bold mb-5 flex items-center gap-2">
              <Plus className="w-5 h-5 text-primary" /> 새 업무 추가
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="text-sm font-semibold mb-1.5 block">업무명 *</label>
                <input
                  type="text"
                  placeholder="UI 디자인 시안 작성"
                  value={newTask.title}
                  onChange={e => setNewTask({...newTask, title: e.target.value})}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <div>
                <label className="text-sm font-semibold mb-1.5 block">설명 (선택)</label>
                <textarea
                  placeholder="세부 내용..."
                  value={newTask.description}
                  onChange={e => setNewTask({...newTask, description: e.target.value})}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  rows={3}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">시작일</label>
                  <input
                    type="date"
                    value={newTask.wbsStart}
                    onChange={e => setNewTask({...newTask, wbsStart: e.target.value})}
                    className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">마감일</label>
                  <input
                    type="date"
                    value={newTask.wbsEnd}
                    onChange={e => setNewTask({...newTask, wbsEnd: e.target.value})}
                    className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
              </div>
              <div>
                <label className="text-sm font-semibold mb-1.5 block">담당자</label>
                <select
                  value={newTask.assigneeId}
                  onChange={e => setNewTask({...newTask, assigneeId: e.target.value})}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                >
                  <option value="">할당하지 않음</option>
                  {users.map(u => (
                    <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-3 mt-8">
              <button onClick={() => setAddModal(false)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5 transition-colors">취소</button>
              <button
                onClick={handleAddTask}
                disabled={!newTask.title.trim() || adding}
                className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {adding ? <Loader2 className="w-4 h-4 animate-spin" /> : "추가하기"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}