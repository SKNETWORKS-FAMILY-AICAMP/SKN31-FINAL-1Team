"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { UserPlus, Search, Settings, MoreVertical, KeyRound, Trash2, ShieldCheck, X, Loader2, CheckCircle2, Briefcase } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { DEPARTMENTS, POSITIONS, JOB_TITLES, STATUS_META, SKILL_SUGGESTIONS, CERT_SUGGESTIONS, PROJECT_SUGGESTIONS } from "@/lib/employeeOptions";
import TagAutocomplete from "@/components/ui/TagAutocomplete";

type EmployeeStatus = "ACTIVE" | "LEAVE" | "RESIGNED" | "LOCKED";

type Employee = {
  id: string;
  name: string;
  email: string;
  role: string;
  department: string | null;
  techStack: string | null;
  certifications: string | null;
  pastProjects: string | null;
  phone: string | null;
  employeeNo: string | null;
  position: string | null;
  jobTitle: string | null;
  status: EmployeeStatus;
  hireDate: string | null;
  resignDate: string | null;
  createdAt: string;
};

const fmtDate = (iso: string | null) => iso ? new Date(iso).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }) : "-";

type FilterStatus = "all" | EmployeeStatus;

export default function MembersPage() {
  const { user, isLoading: authLoading } = useAuth();
  const isPM = user?.role === "PM";
  const router = useRouter();

  // 사이드바/모바일 메뉴에서 링크를 숨기는 것만으로는 URL을 직접 입력하면 그대로 들어와 볼 수
  // 있었다 — 직원관리는 팀원 개인정보를 다루므로 PM이 아니면 대시보드로 돌려보낸다. auth 상태가
  // 아직 localStorage에서 로드되기 전(authLoading)엔 판단을 미룬다 — 안 그러면 실제로는 PM인
  // 사용자도 첫 렌더 순간엔 user가 null이라 잘못 튕겨나간다.
  useEffect(() => {
    if (!authLoading && !isPM) router.replace("/");
  }, [authLoading, isPM, router]);

  const [members, setMembers] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  // 담당자별 "아직 안 끝난" 업무 개수 — 대시보드의 "팀원별 업무량" 위젯엔 상위 6명만 나오고
  // 전체보기로 갈 페이지가 없어서, 팀원 전체를 이미 다루는 이 화면에 붙이는 쪽을 택함.
  const [activeTaskCounts, setActiveTaskCounts] = useState<Record<string, number>>({});
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  // Add Employee Modal
  const [addModal, setAddModal] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newName, setNewName] = useState("");
  const [newDept, setNewDept] = useState("");
  const [newEmployeeNo, setNewEmployeeNo] = useState("");
  const [newPosition, setNewPosition] = useState("");
  const [newJobTitle, setNewJobTitle] = useState("");
  const [newHireDate, setNewHireDate] = useState("");
  const [adding, setAdding] = useState(false);

    // Edit Modal
  const [editModal, setEditModal] = useState<{
    id: string; name: string; department: string; role: string; techStack: string[]; certifications: string[]; phone: string;
    employeeNo: string; position: string; jobTitle: string; status: EmployeeStatus; hireDate: string; resignDate: string; pastProjects: string[];
  } | null>(null);
  const [editing, setEditing] = useState(false);

// Delete Confirm Modal
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const menuRef = useRef<HTMLDivElement>(null);
  const portalMenuRef = useRef<HTMLDivElement>(null);
  // 설정 드롭다운을 클릭한 버튼 기준으로 계산한 화면 좌표(포탈용) — 표 마지막 줄에서 버튼을
  // 누르면, 표 카드에 걸린 overflow-hidden에 가려서 메뉴 아래쪽이 잘려 안 보이던 문제가
  // 있었다(사용자가 실제로 보고 발견함). document.body에 포탈로 띄우고 fixed 좌표로 직접
  // 위치를 잡아서 그 overflow-hidden 밖으로 꺼낸다 — 아래 공간이 부족하면 위로 펼친다.
  const [menuPos, setMenuPos] = useState<{ top?: number; bottom?: number; right: number } | null>(null);

  const showToast = (msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    Promise.all([
      fetch("/api/users").then(r => r.json()),
      fetch("/api/tasks").then(r => r.json()),
    ]).then(([usersRes, tasksRes]) => {
      if (usersRes.success) setMembers(usersRes.data);
      if (tasksRes.success) {
        const counts: Record<string, number> = {};
        for (const t of tasksRes.data) {
          if (!t.assigneeId || t.status === "DONE" || t.status === "CANCELLED") continue;
          counts[t.assigneeId] = (counts[t.assigneeId] ?? 0) + 1;
        }
        setActiveTaskCounts(counts);
      }
    }).finally(() => setLoading(false));
  }, []);

  // Close dropdown when clicking outside — 메뉴 본문이 이제 포탈로 document.body 밑에
  // 따로 떠 있어서(위 menuPos 주석 참고), 트리거 버튼(menuRef)뿐 아니라 포탈된 메뉴 자체
  // (portalMenuRef) 안을 클릭했을 때도 "바깥 클릭"으로 잘못 판정해 닫히지 않게 같이 확인한다.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (portalMenuRef.current?.contains(target)) return;
      setOpenMenuId(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = useMemo(() => {
    let result = members;
    if (filterStatus !== "all") result = result.filter(m => m.status === filterStatus);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(m =>
        m.name.toLowerCase().includes(q) ||
        m.email.toLowerCase().includes(q) ||
        (m.department ?? "").toLowerCase().includes(q) ||
        (m.employeeNo ?? "").toLowerCase().includes(q)
      );
    }
    return result;
  }, [members, search, filterStatus]);

  const statusCounts = {
    all: members.length,
    ACTIVE: members.filter(m => m.status === "ACTIVE").length,
    LEAVE: members.filter(m => m.status === "LEAVE").length,
    RESIGNED: members.filter(m => m.status === "RESIGNED").length,
    LOCKED: members.filter(m => m.status === "LOCKED").length,
  };

    const handleEditEmployee = async () => {
    if (!editModal) return;
    setEditing(true);
    const res = await fetch(`/api/users/${editModal.id}/profile`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: editModal.name,
        department: editModal.department,
        role: editModal.role,
        techStack: editModal.techStack.join(", "),
        certifications: editModal.certifications.join(", "),
        phone: editModal.phone,
        employeeNo: editModal.employeeNo,
        position: editModal.position,
        jobTitle: editModal.jobTitle,
        status: editModal.status,
        hireDate: editModal.hireDate,
        resignDate: editModal.resignDate,
        pastProjects: editModal.pastProjects.join(", "),
      }),
    });
    const data = await res.json();
    setEditing(false);
    if (data.success) {
      setMembers(members.map(m => m.id === editModal.id ? { ...m, ...data.data } : m));
      setEditModal(null);
      showToast("직원 정보가 수정되었습니다.");
    } else {
      showToast("수정에 실패했습니다.", "error");
    }
  };

const handlePasswordReset = async (id: string, name: string) => {
    setProcessingId(id);
    setOpenMenuId(null);
    const res = await fetch(`/api/users/${id}/password-reset`, { method: "POST" });
    const data = await res.json();
    setProcessingId(null);
    if (data.success) showToast(`${name}님의 비밀번호가 1111로 초기화되었습니다.`);
    else showToast("초기화 실패", "error");
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setProcessingId(deleteTarget.id);
    const res = await fetch(`/api/users/${deleteTarget.id}/delete`, { method: "DELETE" });
    const data = await res.json();
    setProcessingId(null);
    setDeleteTarget(null);
    if (data.success) {
      setMembers(prev => prev.filter(m => m.id !== deleteTarget.id));
      showToast(`${deleteTarget.name}님 계정이 삭제되었습니다.`);
    } else showToast("삭제 실패", "error");
  };

  const handleRoleChange = async (id: string, role: string) => {
    const res = await fetch(`/api/users/${id}/role`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (res.ok) {
      setMembers(prev => prev.map(m => m.id === id ? { ...m, role } : m));
      showToast("역할이 변경되었습니다.");
    }
  };

  const handleStatusChange = async (id: string, status: string) => {
    const res = await fetch(`/api/users/${id}/profile`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      // 퇴사로 바꾸면 서버가 퇴사일을 자동으로 채워 응답하므로(반대로 되돌리면 지워서 응답하므로)
      // status만 낙관적으로 반영하면 안 되고 서버가 돌려준 resignDate도 함께 반영해야 한다.
      setMembers(prev => prev.map(m => m.id === id ? { ...m, status: data.data.status, resignDate: data.data.resignDate } : m));
      showToast("계정 상태가 변경되었습니다.");
    }
  };

  const handleAddEmployee = async () => {
    if (!newUsername.trim()) return;
    setAdding(true);
    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: newUsername.trim(),
        name: newName.trim() || newUsername.trim(),
        department: newDept.trim(),
        position: newPosition.trim(),
        jobTitle: newJobTitle.trim(),
        employeeNo: newEmployeeNo.trim(),
        hireDate: newHireDate || undefined,
      }),
    });
    const data = await res.json();
    setAdding(false);
    if (data.success) {
      setMembers(prev => [data.data, ...prev]);
      setAddModal(false);
      setNewUsername(""); setNewName(""); setNewDept("");
      setNewEmployeeNo(""); setNewPosition(""); setNewJobTitle(""); setNewHireDate("");
      showToast(`${data.data.name}님 계정이 생성되었습니다. 초기 비밀번호: 1111`);
    } else {
      showToast(data.error || "생성 실패", "error");
    }
  };

  const skills = (raw: string | null) => raw ? raw.split(",").map(s => s.trim()).filter(Boolean) : [];

  // PM이 아니면 위 useEffect가 리다이렉트를 시작하지만, 그 한 렌더 사이에 팀원 개인정보가
  // 잠깐이라도 그려지지 않도록 여기서도 막는다.
  if (authLoading || !isPM) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary/50" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-6xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      {/* Toast */}
      {toast && (
        <div className={cn(
          "fixed top-6 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-3 px-4 py-3 rounded-xl shadow-xl border text-sm font-semibold animate-in slide-in-from-top-2 duration-300",
          toast.type === "success"
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
            : "bg-red-500/10 border-red-500/30 text-red-400"
        )}>
          {toast.type === "success" ? <CheckCircle2 className="w-4 h-4" /> : <X className="w-4 h-4" />}
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-muted-foreground mt-1">팀원 계정을 관리하고 역할과 권한을 설정하세요.</p>
        </div>
        {isPM && (
          <button
            onClick={() => setAddModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-semibold text-sm transition-colors shadow-md"
          >
            <UserPlus className="w-4 h-4" />
            직원 추가
          </button>
        )}
      </div>

      {/* Search + Status Tabs */}
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 justify-between">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="이름, 이메일, 부서, 사번으로 검색..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 lg:w-80"
          />
        </div>
        <div className="flex items-center gap-1 p-1 bg-black/5 dark:bg-white/5 rounded-xl w-max">
          {([
            { key: "all", label: "전체" },
            { key: "ACTIVE", label: "활성" },
            { key: "LEAVE", label: "휴직" },
            { key: "RESIGNED", label: "퇴사" },
            { key: "LOCKED", label: "잠금" },
          ] as { key: FilterStatus; label: string }[]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilterStatus(tab.key)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5",
                filterStatus === tab.key ? "bg-white dark:bg-white/10 text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab.label}
              <span className={cn(
                "px-1.5 py-0.5 rounded-full text-[9px] font-black",
                filterStatus === tab.key ? "bg-primary/10 text-primary" : "bg-black/10 dark:bg-white/10"
              )}>
                {statusCounts[tab.key]}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="glass rounded-xl border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-black/10 dark:bg-white/5 text-muted-foreground">
              <tr>
                <th className="px-6 py-4 font-semibold">직원</th>
                <th className="px-6 py-4 font-semibold whitespace-nowrap">부서 / 직급 /<br />직무</th>
                <th className="px-6 py-4 font-semibold">기술 스택</th>
                <th className="px-6 py-4 font-semibold whitespace-nowrap">입사일 /<br />퇴사일</th>
                <th className="px-6 py-4 font-semibold">역할</th>
                <th className="px-6 py-4 font-semibold">상태</th>
                <th className="px-6 py-4 font-semibold">업무량</th>
                {isPM && <th className="px-6 py-4 font-semibold text-center">설정</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr><td colSpan={8} className="py-16 text-center"><Loader2 className="w-6 h-6 animate-spin text-primary mx-auto" /></td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={8} className="py-16 text-center text-muted-foreground">검색 결과가 없습니다.</td></tr>
              ) : (
                filtered.map(member => (
                  <tr key={member.id} className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                    {/* Name + Email */}
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                          {member.name.charAt(0)}
                        </div>
                        <div>
                          <p className="font-semibold">{member.name}</p>
                          <p className="text-xs text-muted-foreground">{member.email}</p>
                          {member.phone && <p className="text-xs text-muted-foreground">{member.phone}</p>}
                        </div>
                      </div>
                    </td>

                    {/* Department / Position / Job Title */}
                    <td className="px-6 py-4 text-muted-foreground whitespace-nowrap">
                      <p>{member.department || "-"} {member.position ? `· ${member.position}` : ""}</p>
                      <p className="text-xs">{member.jobTitle || "-"}{member.employeeNo ? ` · ${member.employeeNo}` : ""}</p>
                    </td>

                    {/* Skills + Certs */}
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {skills(member.techStack).slice(0, 3).map((s, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-semibold">{s}</span>
                        ))}
                        {skills(member.techStack).length > 3 && (
                          <span className="text-[10px] text-muted-foreground">+{skills(member.techStack).length - 3}</span>
                        )}
                        {skills(member.certifications).slice(0, 2).map((c, i) => (
                          <span key={`c${i}`} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-semibold">{c}</span>
                        ))}
                      </div>
                    </td>

                    {/* Hire / Resign date */}
                    <td className="px-6 py-4 text-muted-foreground whitespace-nowrap">
                      <p>{fmtDate(member.hireDate)}</p>
                      {member.status === "RESIGNED" && (
                        <p className="text-xs text-red-400 mt-0.5">퇴사 {fmtDate(member.resignDate)}</p>
                      )}
                    </td>

                    {/* Role */}
                    <td className="px-6 py-4">
                      {isPM ? (
                        <select
                          value={member.role}
                          onChange={e => handleRoleChange(member.id, e.target.value)}
                          className={cn(
                            "appearance-none bg-transparent border rounded-lg px-3 py-1.5 text-xs font-semibold cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/40",
                            member.role === "PM" ? "text-emerald-400 border-emerald-400/30" : "text-muted-foreground border-border"
                          )}
                        >
                          <option value="PM">PM</option>
                          <option value="EMPLOYEE">일반 멤버</option>
                          <option value="GUEST">게스트</option>
                        </select>
                      ) : (
                        <span className={cn(
                          "px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap",
                          member.role === "PM" ? "bg-emerald-500/10 text-emerald-400" : "bg-black/10 dark:bg-white/10 text-muted-foreground"
                        )}>
                          {member.role === "PM" ? "PM" : "일반 멤버"}
                        </span>
                      )}
                    </td>

                    {/* Status */}
                    <td className="px-6 py-4">
                      {isPM ? (
                        <select
                          value={member.status}
                          onChange={e => handleStatusChange(member.id, e.target.value)}
                          className={cn(
                            "appearance-none bg-transparent border rounded-lg px-3 py-1.5 text-xs font-semibold cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/40",
                            STATUS_META[member.status].selectClass
                          )}
                        >
                          {Object.keys(STATUS_META).map(s => (
                            <option key={s} value={s}>{STATUS_META[s].label}</option>
                          ))}
                        </select>
                      ) : (
                        <span className={cn(
                          "px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap",
                          STATUS_META[member.status].badgeClass
                        )}>
                          {STATUS_META[member.status].label}
                        </span>
                      )}
                    </td>

                    {/* Workload — PM은 업무 배정 대상이 아니라 집계 자체가 의미 없어 "-"로 표시 */}
                    <td className="px-6 py-4">
                      {member.role === "PM" ? (
                        <span className="text-xs text-muted-foreground">-</span>
                      ) : (
                        <span className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap",
                          (activeTaskCounts[member.id] ?? 0) > 0 ? "bg-primary/10 text-primary" : "bg-black/5 dark:bg-white/5 text-muted-foreground"
                        )}>
                          <Briefcase className="w-3 h-3 shrink-0" /> {activeTaskCounts[member.id] ?? 0}건
                        </span>
                      )}
                    </td>

                    {/* Settings (PM only) */}
                    {isPM && (
                      <td className="px-6 py-4 text-center relative">
                        <div className="relative inline-block" ref={openMenuId === member.id ? menuRef : undefined}>
                          <button
                            onClick={(e) => {
                              if (openMenuId === member.id) {
                                setOpenMenuId(null);
                                return;
                              }
                              const rect = e.currentTarget.getBoundingClientRect();
                              const menuHeight = 176; // 메뉴 항목 3개 + 구분선 기준 대략치
                              const spaceBelow = window.innerHeight - rect.bottom;
                              setMenuPos(
                                spaceBelow >= menuHeight
                                  ? { top: rect.bottom + 8, right: window.innerWidth - rect.right }
                                  : { bottom: window.innerHeight - rect.top + 8, right: window.innerWidth - rect.right }
                              );
                              setOpenMenuId(member.id);
                            }}
                            disabled={processingId === member.id}
                            className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"
                          >
                            {processingId === member.id
                              ? <Loader2 className="w-4 h-4 animate-spin" />
                              : <MoreVertical className="w-4 h-4" />}
                          </button>

                          {openMenuId === member.id && menuPos && createPortal(
                            <div
                              ref={portalMenuRef}
                              style={{ position: "fixed", top: menuPos.top, bottom: menuPos.bottom, right: menuPos.right }}
                              className="z-50 w-48 glass border border-border rounded-xl shadow-xl overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
                              <button
                                onClick={() => handlePasswordReset(member.id, member.name)}
                                className="w-full flex items-center gap-2.5 px-4 py-3 text-sm hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left"
                              >
                                <KeyRound className="w-4 h-4 text-orange-400" />
                                비밀번호 초기화 (1111)
                              </button>
                              <button
                                onClick={() => {
                                  setEditModal({
                                    id: member.id, name: member.name, department: member.department || "", role: member.role,
                                    techStack: skills(member.techStack), certifications: skills(member.certifications), phone: member.phone || "",
                                    employeeNo: member.employeeNo || "", position: member.position || "", jobTitle: member.jobTitle || "",
                                    status: member.status, hireDate: member.hireDate ? member.hireDate.slice(0, 10) : "",
                                    resignDate: member.resignDate ? member.resignDate.slice(0, 10) : "",
                                    pastProjects: skills(member.pastProjects),
                                  });
                                  setOpenMenuId(null);
                                }}
                                className="w-full flex items-center gap-2.5 px-4 py-3 text-sm hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left"
                              >
                                <Settings className="w-4 h-4 text-blue-400" />
                                정보 수정
                              </button>
                              <div className="border-t border-border" />
                              <button
                                onClick={() => { setDeleteTarget({ id: member.id, name: member.name }); setOpenMenuId(null); }}
                                className="w-full flex items-center gap-2.5 px-4 py-3 text-sm hover:bg-red-500/10 transition-colors text-left text-red-400"
                              >
                                <Trash2 className="w-4 h-4" />
                                계정 삭제
                              </button>
                            </div>,
                            document.body
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Role Legend */}
      <div className="grid md:grid-cols-3 gap-4 mt-8">
        {[
          { role: "PM", color: "border-t-emerald-500", textColor: "text-emerald-500", perms: ["프로젝트 생성/삭제", "직원 추가 및 역할 변경", "비밀번호 초기화", "승인 및 반려 처리"] },
          { role: "일반 멤버", color: "border-t-primary", textColor: "text-primary", perms: ["할 일 생성 및 수정", "칸반 보드 상태 변경", "검토 요청", "본인 프로필 수정"] },
          { role: "게스트", color: "border-t-muted-foreground", textColor: "text-muted-foreground", perms: ["읽기 전용 열람", "코멘트 작성", "수정/생성 불가"] },
        ].map(item => (
          <div key={item.role} className={cn("glass p-5 rounded-xl border border-border border-t-4", item.color)}>
            <h4 className={cn("font-bold mb-3", item.textColor)}>{item.role}</h4>
            <ul className="space-y-1.5">
              {item.perms.map((p, i) => (
                <li key={i} className="flex items-center gap-2 text-sm text-muted-foreground">
                  <ShieldCheck className={cn("w-3.5 h-3.5 shrink-0", item.textColor)} /> {p}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Add Employee Modal */}
      {addModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-xl font-bold flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-primary" /> 직원 추가
              </h3>
              <button onClick={() => setAddModal(false)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-semibold mb-1.5 block">아이디 <span className="text-red-400">*</span></label>
                <div className="flex items-center border border-border rounded-xl overflow-hidden bg-black/5 dark:bg-white/5">
                  <input
                    type="text"
                    placeholder="아이디 입력"
                    value={newUsername}
                    onChange={e => setNewUsername(e.target.value)}
                    className="flex-1 px-4 py-2.5 bg-transparent text-sm focus:outline-none"
                    onKeyDown={e => e.key === "Enter" && handleAddEmployee()}
                  />
                  <span className="pr-4 text-xs text-muted-foreground whitespace-nowrap">@heyzzabi.com</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">초기 비밀번호: <strong>1111</strong></p>
              </div>

              <div>
                <label className="text-sm font-semibold mb-1.5 block">이름 (비어있으면 아이디로 설정)</label>
                <input
                  type="text"
                  placeholder="홍길동"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">부서 (선택)</label>
                  <select
                    value={newDept}
                    onChange={e => setNewDept(e.target.value)}
                    className="w-full px-3 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                  >
                    <option value="">선택 안 함</option>
                    {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">직급 (선택)</label>
                  <select
                    value={newPosition}
                    onChange={e => setNewPosition(e.target.value)}
                    className="w-full px-3 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                  >
                    <option value="">선택 안 함</option>
                    {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">직무 (선택)</label>
                  <select
                    value={newJobTitle}
                    onChange={e => setNewJobTitle(e.target.value)}
                    className="w-full px-3 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                  >
                    <option value="">선택 안 함</option>
                    {JOB_TITLES.map(j => <option key={j} value={j}>{j}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">사번 (선택)</label>
                  <input
                    type="text"
                    placeholder="예: 2026001"
                    value={newEmployeeNo}
                    onChange={e => setNewEmployeeNo(e.target.value)}
                    className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-semibold mb-1.5 block">입사일 (선택)</label>
                <input
                  type="date"
                  value={newHireDate}
                  onChange={e => setNewHireDate(e.target.value)}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <p className="text-xs text-muted-foreground">
                기술 스택 · 자격증 · 주요 프로젝트 · 연락처는 최초 로그인 시 본인이 직접 입력합니다.
              </p>
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => setAddModal(false)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={handleAddEmployee}
                disabled={!newUsername.trim() || adding}
                className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-40 flex items-center justify-center gap-2"
              >
                {adding ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
                생성하기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4">
            <h3 className="text-xl font-bold mb-2 flex items-center gap-2 text-red-400">
              <Trash2 className="w-5 h-5" /> 계정 삭제
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              <span className="font-bold text-foreground">"{deleteTarget.name}"</span> 님의 계정을 삭제하시겠습니까?<br />
              이 작업은 되돌릴 수 없습니다.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteTarget(null)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={handleDelete}
                disabled={processingId !== null}
                className="flex-1 py-2.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-semibold hover:bg-red-500/20 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {processingId ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                삭제
              </button>
            </div>
          </div>
        </div>
      )}
    

      {/* Edit Modal — 필드가 많아 세로로 나열하면 모달이 지나치게 길어지므로 좌(기본정보)/우(스택·이력) 2단 레이아웃으로 분리 */}
      {editModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold flex items-center gap-2">
                <Settings className="w-5 h-5 text-primary" /> 정보 수정
              </h3>
              <button onClick={() => setEditModal(null)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
              {/* 좌측: 이름/부서/권한/직급/직무/사번/입사일/계정상태 — 기본 인사 정보 */}
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">이름</label>
                  <input
                    type="text"
                    value={editModal.name}
                    onChange={e => setEditModal({ ...editModal, name: e.target.value })}
                    className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">부서</label>
                    <select
                      value={editModal.department}
                      onChange={e => setEditModal({ ...editModal, department: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                    >
                      <option value="">선택 안 함</option>
                      {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">권한</label>
                    <select
                      value={editModal.role}
                      onChange={e => setEditModal({ ...editModal, role: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                    >
                      <option value="EMPLOYEE">일반 멤버</option>
                      <option value="PM">PM</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">직급</label>
                    <select
                      value={editModal.position}
                      onChange={e => setEditModal({ ...editModal, position: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                    >
                      <option value="">선택 안 함</option>
                      {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">직무</label>
                    <select
                      value={editModal.jobTitle}
                      onChange={e => setEditModal({ ...editModal, jobTitle: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                    >
                      <option value="">선택 안 함</option>
                      {JOB_TITLES.map(j => <option key={j} value={j}>{j}</option>)}
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">사번</label>
                    <input
                      type="text"
                      value={editModal.employeeNo}
                      onChange={e => setEditModal({ ...editModal, employeeNo: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">입사일</label>
                    <input
                      type="date"
                      value={editModal.hireDate}
                      onChange={e => setEditModal({ ...editModal, hireDate: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">계정 상태</label>
                    <select
                      value={editModal.status}
                      onChange={e => setEditModal({ ...editModal, status: e.target.value as EmployeeStatus })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                    >
                      {Object.keys(STATUS_META).map(s => <option key={s} value={s}>{STATUS_META[s].label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">퇴사일</label>
                    <input
                      type="date"
                      value={editModal.resignDate}
                      onChange={e => setEditModal({ ...editModal, resignDate: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  </div>
                </div>
              </div>

              {/* 우측: 기술스택/자격증/주요프로젝트/연락처 — 태그형 이력 정보 */}
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">기술 스택</label>
                  <TagAutocomplete
                    value={editModal.techStack}
                    onChange={techStack => setEditModal({ ...editModal, techStack })}
                    suggestions={SKILL_SUGGESTIONS}
                    placeholder="목록에서 선택"
                    allowCustom={false}
                  />
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">자격증</label>
                  <TagAutocomplete
                    value={editModal.certifications}
                    onChange={certifications => setEditModal({ ...editModal, certifications })}
                    suggestions={CERT_SUGGESTIONS}
                    placeholder="목록에서 선택"
                    allowCustom={false}
                  />
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">주요 프로젝트</label>
                  <TagAutocomplete
                    value={editModal.pastProjects}
                    onChange={pastProjects => setEditModal({ ...editModal, pastProjects })}
                    suggestions={PROJECT_SUGGESTIONS}
                    placeholder="목록에서 선택"
                    allowCustom={false}
                  />
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">연락처</label>
                  <input
                    type="text"
                    value={editModal.phone}
                    onChange={e => setEditModal({ ...editModal, phone: e.target.value })}
                    placeholder="010-0000-0000"
                    className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => setEditModal(null)} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
              <button
                onClick={handleEditEmployee}
                disabled={!editModal.name.trim() || editing}
                className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-40 flex items-center justify-center gap-2"
              >
                {editing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Settings className="w-4 h-4" />}
                저장하기
              </button>
            </div>
          </div>
        </div>
      )}
</div>
  );
}