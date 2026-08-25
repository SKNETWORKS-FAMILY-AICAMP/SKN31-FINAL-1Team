"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  PieChart, Pie, Cell, Tooltip
} from "recharts";
import {
  GitPullRequest, AlertTriangle, CheckCircle2, Clock,
  Activity, Users, FolderKanban, Loader2, ArrowUpRight,
  PlusCircle
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import { useAuth } from "@/lib/auth";

type ProjectStat = {
  id: string;
  name: string;
  totalTasks: number;
  doneTasks: number;
  progress: number;
};

type ActivityLog = {
  projectId: string;
  projectName: string;
  taskTitle: string;
  status: string;
  statusLabel: string;
  assigneeName: string | null;
  updatedAt: string;
};

const STATUS_COLORS: Record<string, string> = {
  BACKLOG: "bg-gray-500",
  PENDING_APPROVAL: "bg-orange-500",
  IN_PROGRESS: "bg-blue-500",
  DONE: "bg-emerald-500",
};

// statusChart는 API가 이미 한글 라벨로 만들어 내려주는데(dashboard/route.ts), 클릭 시 /tasks로
// 보내려면 원래 상태 코드가 필요해서 여기서 역매핑한다.
const STATUS_CODE_BY_LABEL: Record<string, string> = {
  "대기": "BACKLOG",
  "배분승인대기": "PENDING_APPROVAL",
  "진행 중": "IN_PROGRESS",
  "완료": "DONE",
};

export default function OverviewView() {
  const { user } = useAuth();
  const router = useRouter();
  const isPM = user?.role === "PM";
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const url = isPM ? "/api/dashboard" : `/api/dashboard?scope=me&userId=${user.id}`;
    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        if (data && !data.error) {
          setStats(data);
        }
      })
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [user, isPM]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-20 text-red-500">
        데이터를 불러오지 못했습니다.
      </div>
    );
  }

  const { summary, statusChart, workload, activityLog, projectList } = stats;

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-in fade-in duration-500">
      
      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 pt-2">
        <StatCard
          href="/tasks"
          icon={<GitPullRequest className="w-5 h-5 text-blue-500" />}
          label={isPM ? "전체 업무" : "내 업무"}
          value={summary.totalTasks || 0}
        />
        <StatCard
          href="/tasks"
          icon={<Activity className="w-5 h-5 text-purple-500" />}
          label="진행 중"
          value={summary.inProgress || 0}
        />
        <StatCard
          href="/approvals"
          icon={<Clock className="w-5 h-5 text-orange-500" />}
          // PM/MEMBER 둘 다 같은 값(pendingApproval)을 보므로 라벨도 통일한다 — 예전엔 MEMBER 쪽만
          // "검토 요청중"이라 문서 검토 상태(PENDING_REVIEW)와 헷갈렸음(둘은 서로 다른 개념).
          label="배분승인대기"
          value={summary.pendingApproval || 0}
        />
        <StatCard
          href="/tasks"
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-500" />}
          label="완료"
          value={summary.done || 0}
        />
        <StatCard
          href="/tasks"
          icon={<AlertTriangle className="w-5 h-5 text-red-500" />}
          label="완료율"
          value={`${summary.completionRate || 0}%`}
        />
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 grid-flow-row-dense">
        
        {/* Activity (2 columns) */}
        <div className="lg:col-span-2">
          <div className="glass p-6 rounded-xl h-full">
            <div className="flex justify-between items-center mb-5">
              <h3 className="text-base font-bold flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-500" /> {isPM ? "최근 업무 활동" : "내 최근 업무 활동"}
              </h3>
              <Link href="/tasks" className="flex items-center gap-1 text-xs text-primary font-semibold hover:underline transition-colors">전체보기 <ArrowUpRight className="w-3.5 h-3.5" /></Link>
            </div>
            <div className="space-y-3">
              {activityLog.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">아직 활동 내역이 없습니다.</p>
              ) : (
                activityLog.slice(0, 5).map((log: ActivityLog, i: number) => (
                  <Link key={i} href={`/projects/${log.projectId}`} className="flex items-start gap-3 pb-3 border-b border-foreground/5 last:border-0 last:pb-0 group">
                    <div className={cn("w-2 h-2 rounded-full mt-1.5 shrink-0", STATUS_COLORS[log.status] ?? "bg-gray-500")} />
                    <div className="flex-1 min-w-0">
                      {/* 단일 프로젝트 운영 전제라 프로젝트명 배지는 중복 정보 — 업무 제목만 표시 */}
                      <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">
                        {log.taskTitle}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {log.statusLabel}
                        {log.assigneeName && ` · ${log.assigneeName}`}
                      </p>
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {formatDistanceToNow(new Date(log.updatedAt), { addSuffix: true, locale: ko })}
                    </span>
                  </Link>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Status Chart (1 column) */}
        <div className="lg:col-span-1 self-start">
          <div className="glass p-6 rounded-xl">
            <h3 className="text-sm font-bold mb-4">업무 상태 분포</h3>
            {statusChart.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">데이터 없음</p>
            ) : (
              <>
                <div className="h-[180px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={statusChart} innerRadius={55} outerRadius={75} paddingAngle={3} dataKey="value">
                        {statusChart.map((entry: any, index: number) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={entry.color}
                            cursor="pointer"
                            onClick={() => router.push(`/tasks?status=${STATUS_CODE_BY_LABEL[entry.name] ?? ""}`)}
                          />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(v: any) => [`${v}건`, ""]}
                        contentStyle={{ background: "rgba(0,0,0,0.85)", border: "none", borderRadius: "8px", fontSize: "12px" }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2 mt-2">
                  {statusChart.map((d: any) => (
                    <Link
                      key={d.name}
                      href={`/tasks?status=${STATUS_CODE_BY_LABEL[d.name] ?? ""}`}
                      className="flex justify-between text-xs font-medium hover:text-primary transition-colors group"
                    >
                      <span className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: d.color }} />
                        {d.name}
                      </span>
                      <span className="flex items-center gap-1">
                        {d.value}건 <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </span>
                    </Link>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Projects (2 columns for PM, full width for personal view) */}
        <div className={isPM ? "lg:col-span-2" : "lg:col-span-3"}>
          <div className="glass p-6 rounded-xl h-full">
            <div className="flex justify-between items-center mb-5">
              <h3 className="text-base font-bold flex items-center gap-2">
                <FolderKanban className="w-5 h-5 text-emerald-500" /> {isPM ? "진행 중인 프로젝트" : "내가 참여 중인 프로젝트"}
              </h3>
              {isPM && (
                <Link
                  href="/project/new"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 rounded-lg text-xs font-semibold transition-colors"
                >
                  <PlusCircle className="w-4 h-4" /> 새 프로젝트
                </Link>
              )}
            </div>
            {projectList.length === 0 ? (
              <div className="py-10 text-center text-muted-foreground space-y-2">
                <FolderKanban className="w-10 h-10 mx-auto opacity-20" />
                <p className="text-sm">{isPM ? "아직 프로젝트가 없습니다." : "아직 참여 중인 프로젝트가 없습니다."}</p>
                {isPM && (
                  <Link href="/project/new" className="inline-block mt-2 px-4 py-2 bg-primary text-white rounded-lg text-sm font-bold">
                    첫 프로젝트 만들기
                  </Link>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {projectList.map((p: ProjectStat) => (
                  <Link key={p.id} href={`/projects/${p.id}`} className="block group">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-semibold group-hover:text-primary transition-colors flex items-center gap-1">
                        {p.name}
                        <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {p.doneTasks}/{p.totalTasks}건 · {p.progress}%
                      </span>
                    </div>
                    <div className="h-2 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${p.progress}%` }}
                      />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Workload (1 column) — team-wide, PM only */}
        {isPM && (
          <div className="lg:col-span-1">
            <div className="glass p-6 rounded-xl h-full">
              <h3 className="text-sm font-bold flex items-center gap-2 mb-4">
                <Users className="w-4 h-4 text-blue-500" /> 팀원별 업무량
              </h3>
              {workload.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">담당이 지정된 업무가 없습니다.</p>
              ) : (
                <div className="h-[180px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={workload} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#88888820" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: "#888", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#888", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}건`} />
                      <Tooltip
                        formatter={(v: any) => [`${v}건`, "할당 업무"]}
                        contentStyle={{ background: "rgba(0,0,0,0.85)", border: "none", borderRadius: "8px", fontSize: "12px" }}
                      />
                      <Bar dataKey="taskCount" fill="#6366f1" radius={[4, 4, 0, 0]} barSize={20} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

function StatCard({ icon, label, value, href }: { icon: React.ReactNode; label: string; value: string | number; href: string }) {
  return (
    <Link
      href={href}
      className="glass p-4 rounded-xl flex flex-col justify-between group hover:bg-black/5 dark:hover:bg-white/5 transition-colors border border-border hover:border-primary/30"
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="p-2 bg-black/5 dark:bg-white/10 rounded-lg group-hover:scale-110 transition-transform">
          {icon}
        </div>
        <span className="text-xs font-semibold text-muted-foreground group-hover:text-foreground transition-colors">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold">{value}</span>
      </div>
    </Link>
  );
}
