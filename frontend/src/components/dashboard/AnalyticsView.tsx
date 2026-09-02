"use client";

import { useEffect, useState } from "react";
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area, XAxis, YAxis, 
  CartesianGrid, ResponsiveContainer, PieChart, Pie, Cell, Tooltip
} from "recharts";
import { Loader2, TrendingUp, Users, Clock, Target, CheckCircle2, AlertTriangle, Layers } from "lucide-react";
import { apiFetch } from "@/lib/api/client";

type TaskDto = {
  id: number;
  project: number | null;
  assigned_user_name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

type ProjectDto = { id: number; name: string };

// 백엔드엔 통계 전용 API가 없다 — 업무 원본을 받아 화면에서 직접 집계한다. 완료 시각을 따로
// 기록하지 않으므로 "완료 시점"은 상태가 마지막으로 바뀐 시각(updated_at)으로 근사한다.
function buildAnalytics(tasks: TaskDto[], projects: ProjectDto[]) {
  const days: string[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push(d.toISOString().slice(0, 10));
  }
  const weeklyCompletion = days.map(date => ({
    date: date.slice(5),
    count: tasks.filter(t => t.status === "COMPLETED" && t.updated_at.slice(0, 10) === date).length,
  }));

  const contributionMap = new Map<string, { done: number; inProgress: number }>();
  tasks.forEach(t => {
    const name = t.assigned_user_name ?? "미배정";
    const entry = contributionMap.get(name) ?? { done: 0, inProgress: 0 };
    if (t.status === "COMPLETED") entry.done += 1;
    if (t.status === "IN_PROGRESS") entry.inProgress += 1;
    contributionMap.set(name, entry);
  });
  const teamContribution = Array.from(contributionMap.entries()).map(([name, v]) => ({ name, ...v }));

  const completedTasks = tasks.filter(t => t.status === "COMPLETED");
  const averageProcessTime = completedTasks.length
    ? Math.round(
        (completedTasks.reduce((sum, t) => sum + (new Date(t.updated_at).getTime() - new Date(t.created_at).getTime()), 0) /
          completedTasks.length / 86400000) * 10
      ) / 10
    : 0;

  const approved = tasks.filter(t => ["APPROVED", "IN_PROGRESS", "COMPLETED"].includes(t.status)).length;
  const rejected = tasks.filter(t => t.status === "REJECTED").length;

  const projectBurndown = projects.map(p => ({
    name: p.name,
    remaining: tasks.filter(t => t.project === p.id && ["PENDING_APPROVAL", "APPROVED", "IN_PROGRESS"].includes(t.status)).length,
  }));

  return {
    weeklyCompletion,
    teamContribution,
    averageProcessTime,
    approvalPassRate: { approved, rejected },
    projectBurndown,
  };
}

export default function AnalyticsPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiFetch<TaskDto[]>("/api/tasks/assignments/"),
      apiFetch<ProjectDto[]>("/api/projects/"),
    ])
      .then(([tasks, projects]) => setData(buildAnalytics(tasks, projects)))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center items-center h-[60vh]"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  if (!data) return <div className="text-center py-20 text-red-500">데이터를 불러오지 못했습니다.</div>;

  const {
    weeklyCompletion, teamContribution, averageProcessTime,
    approvalPassRate, projectBurndown
  } = data;

  const pieData = [
    { name: "승인 통과", value: approvalPassRate.approved, color: "#10b981" },
    { name: "반려/수정", value: approvalPassRate.rejected, color: "#f43f5e" }
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-in fade-in duration-500">
      


      {/* Top 3 KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass p-6 rounded-xl flex items-center gap-4">
          <div className="w-12 h-12 bg-blue-500/20 text-blue-500 rounded-full flex items-center justify-center">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground font-medium">최근 7일 완료 건수</p>
            <h2 className="text-3xl font-bold">{weeklyCompletion.reduce((a:any, b:any) => a + b.count, 0)}<span className="text-sm font-normal text-muted-foreground ml-1">건</span></h2>
          </div>
        </div>
        
        <div className="glass p-6 rounded-xl flex items-center gap-4">
          <div className="w-12 h-12 bg-orange-500/20 text-orange-500 rounded-full flex items-center justify-center">
            <Clock className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground font-medium">평균 업무 처리 기간</p>
            <h2 className="text-3xl font-bold">{averageProcessTime}<span className="text-sm font-normal text-muted-foreground ml-1">일</span></h2>
          </div>
        </div>

        <div className="glass p-6 rounded-xl flex items-center gap-4">
          <div className="w-12 h-12 bg-emerald-500/20 text-emerald-500 rounded-full flex items-center justify-center">
            <Target className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground font-medium">승인 통과율</p>
            <h2 className="text-3xl font-bold">
              {approvalPassRate.approved + approvalPassRate.rejected === 0 
                ? 0 
                : Math.round((approvalPassRate.approved / (approvalPassRate.approved + approvalPassRate.rejected)) * 100)}<span className="text-sm font-normal text-muted-foreground ml-1">%</span>
            </h2>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 1. Weekly Completion Trend */}
        <div className="glass p-6 rounded-xl">
          <h3 className="font-bold mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-blue-500" /> 주간 업무 완료 추이
          </h3>
          <div className="h-[250px] w-full">
            <ResponsiveContainer>
              <LineChart data={weeklyCompletion} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#88888820" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#888", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#888", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "rgba(0,0,0,0.85)", border: "none", borderRadius: "8px", color: "#fff" }} />
                <Line type="monotone" dataKey="count" name="완료 건수" stroke="#3b82f6" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 2. Team Contribution */}
        <div className="glass p-6 rounded-xl">
          <h3 className="font-bold mb-4 flex items-center gap-2">
            <Users className="w-5 h-5 text-purple-500" /> 팀원별 기여도
          </h3>
          <div className="h-[250px] w-full">
            <ResponsiveContainer>
              <BarChart data={teamContribution} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#88888820" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#888", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#888", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "rgba(0,0,0,0.85)", border: "none", borderRadius: "8px", color: "#fff" }} />
                <Bar dataKey="done" name="완료" stackId="a" fill="#10b981" radius={[0, 0, 4, 4]} />
                <Bar dataKey="inProgress" name="진행 중" stackId="a" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 4. Approval Pass Rate */}
        <div className="glass p-6 rounded-xl">
          <h3 className="font-bold mb-4 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" /> 승인 통과율
          </h3>
          <div className="flex items-center h-[250px]">
            <ResponsiveContainer width="50%" height="100%">
              <PieChart>
                <Pie data={pieData} innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                  {pieData.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.color} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "rgba(0,0,0,0.85)", border: "none", borderRadius: "8px", color: "#fff" }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="w-1/2 space-y-4">
              {pieData.map(d => (
                <div key={d.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: d.color }}/>
                      {d.name}
                    </span>
                    <span className="font-bold text-sm">{d.value}건</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 6. Project Burndown (Remaining vs Completed) */}
        <div className="glass p-6 rounded-xl">
          <h3 className="font-bold mb-4 flex items-center gap-2">
            <Layers className="w-5 h-5 text-orange-500" /> 프로젝트 남은 업무 잔량
          </h3>
          <div className="h-[250px] w-full">
            <ResponsiveContainer>
              <AreaChart data={projectBurndown} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#88888820" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#888", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#888", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "rgba(0,0,0,0.85)", border: "none", borderRadius: "8px", color: "#fff" }} />
                <Area type="monotone" dataKey="remaining" name="남은 업무" stroke="#f97316" fill="#f97316" fillOpacity={0.2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>
    </div>
  );
}
