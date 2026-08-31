"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { UserPlus, Search, Settings, MoreVertical, KeyRound, Trash2, ShieldCheck, X, Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import { STATUS_META, PROJECT_SUGGESTIONS } from "@/lib/employeeOptions";
import TagAutocomplete from "@/components/ui/TagAutocomplete";

type EmployeeStatus = "ACTIVE" | "LEAVE" | "RESIGNED" | "LOCKED";

// Django CommonCode 응답(부서/직급/직무/상태) 최소 형태 — GET /api/common/codes/?group_code=...
type CodeOption = { code_id: string; code_name: string };

type Employee = {
  id: string;
  username: string;
  firstName: string;
  lastName: string;
  name: string;
  email: string;
  phone: string | null;
  empNo: string | null;
  deptCode: string | null;
  deptName: string | null;
  positionCode: string | null;
  positionName: string | null;
  jobRoleCode: string | null;
  jobRoleName: string | null;
  // 이 화면은 PM/일반 멤버 이분법만 다룬다 — 실제 USER_ROLE 공통코드엔 TEAM_LEAD도 있지만
  // (frontend/src/lib/api/mappers.ts의 toUser()와 동일한 단순화) 여기서는 다루지 않는다.
  roleCode: "ADMIN" | "EMPLOYEE" | string | null;
  role: "PM" | "MEMBER";
  status: EmployeeStatus;
  hireDate: string | null;
  resignDate: string | null;
  pastProjects: string[];
  // 기술 스택/자격증은 UserSkill/UserCertification이 CommonCode를 참조하는 구조라 이 화면에서
  // 바로 수정하게 하려면 스킬 그룹별 선택 UI가 통째로 더 필요하다 — 이번 재설계 범위 밖이라
  // 조회만 지원한다.
  skills: string[];
  certifications: string[];
};

const fmtDate = (iso: string | null) => iso ? new Date(iso).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }) : "-";

function toEmployee(dto: any): Employee {
  const lastName = dto.last_name ?? "";
  const firstName = dto.first_name ?? "";
  const name = lastName || firstName ? `${lastName}${firstName}` : dto.username;
  const isPM = dto.role_info?.code_id === "ADMIN" || dto.is_staff;
  return {
    id: String(dto.id),
    username: dto.username,
    firstName,
    lastName,
    name,
    email: dto.email || "",
    phone: dto.phone ?? null,
    empNo: dto.emp_no ?? null,
    deptCode: dto.dept_code ?? null,
    deptName: dto.dept_info?.code_name ?? null,
    positionCode: dto.position_code ?? null,
    positionName: dto.position_info?.code_name ?? null,
    jobRoleCode: dto.job_role_code ?? null,
    jobRoleName: dto.job_role_info?.code_name ?? null,
    roleCode: dto.role_info?.code_id ?? (dto.is_staff ? "ADMIN" : null),
    role: isPM ? "PM" : "MEMBER",
    // status_code가 비어있는 시드/신규 계정은 활성으로 취급한다(퇴사 처리를 거치지 않았다면
    // 사실상 활성이라 화면에 빈 배지 대신 "활성"을 보여주는 편이 맞다).
    status: (dto.status_info?.code_id as EmployeeStatus) ?? "ACTIVE",
    hireDate: dto.hire_date ?? null,
    resignDate: dto.resign_date ?? null,
    pastProjects: dto.past_projects ? String(dto.past_projects).split(",").map((s: string) => s.trim()).filter(Boolean) : [],
    skills: (dto.skills ?? []).map((s: any) => s.skill_name),
    certifications: (dto.certifications ?? []).map((c: any) => c.cert_name),
  };
}

async function fetchCodeOptions(groupCode: string): Promise<CodeOption[]> {
  const list = await apiFetch<CodeOption[]>(`/api/common/codes/?group_code=${groupCode}`);
  return list.map(c => ({ code_id: c.code_id, code_name: c.code_name }));
}

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
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  // 부서/직급/직무/상태 드롭다운 옵션 — Django의 CommonCode(USER_DEPARTMENT 등)에서 가져온다.
  // 예전엔 employeeOptions.ts에 하드코딩된 한글 라벨 문자열을 그대로 department/position 값으로
  // 저장했는데, 실제 백엔드는 dept_code 같은 코드ID(FK)를 요구해서 그 값들을 그대로 못 쓴다.
  const [deptOptions, setDeptOptions] = useState<CodeOption[]>([]);
  const [positionOptions, setPositionOptions] = useState<CodeOption[]>([]);
  const [jobRoleOptions, setJobRoleOptions] = useState<CodeOption[]>([]);
  const [statusOptions, setStatusOptions] = useState<CodeOption[]>([]);

  // Add Employee Modal
  const [addModal, setAddModal] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newLastName, setNewLastName] = useState("");
  const [newFirstName, setNewFirstName] = useState("");
  const [newDept, setNewDept] = useState("");
  const [newEmployeeNo, setNewEmployeeNo] = useState("");
  const [newPosition, setNewPosition] = useState("");
  const [newJobRole, setNewJobRole] = useState("");
  const [newHireDate, setNewHireDate] = useState("");
  const [adding, setAdding] = useState(false);

  // Edit Modal
  const [editModal, setEditModal] = useState<{
    id: string; lastName: string; firstName: string; department: string; roleCode: string;
    phone: string; employeeNo: string; position: string; jobRole: string; status: EmployeeStatus;
    hireDate: string; resignDate: string; pastProjects: string[];
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
      apiFetch<any[]>("/api/users/"),
      fetchCodeOptions("USER_DEPARTMENT"),
      fetchCodeOptions("USER_POSITION"),
      fetchCodeOptions("USER_JOB_ROLE"),
      fetchCodeOptions("USER_STATUS"),
    ])
      .then(([users, depts, positions, jobRoles, statuses]) => {
        setMembers(users.map(toEmployee));
        setDeptOptions(depts);
        setPositionOptions(positions);
        setJobRoleOptions(jobRoles);
        setStatusOptions(statuses);
      })
      .catch(err => showToast(err.message || "직원 목록을 불러오지 못했습니다.", "error"))
      .finally(() => setLoading(false));
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
        m.username.toLowerCase().includes(q) ||
        (m.deptName ?? "").toLowerCase().includes(q) ||
        (m.empNo ?? "").toLowerCase().includes(q)
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
    try {
      const dto = await apiFetch<any>(`/api/users/${editModal.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          last_name: editModal.lastName,
          first_name: editModal.firstName,
          dept_code: editModal.department || null,
          role_code: editModal.roleCode || null,
          position_code: editModal.position || null,
          job_role_code: editModal.jobRole || null,
          phone: editModal.phone || null,
          emp_no: editModal.employeeNo || null,
          status_code: editModal.status || null,
          hire_date: editModal.hireDate || null,
          resign_date: editModal.resignDate || null,
          past_projects: editModal.pastProjects.join(","),
        }),
      });
      setMembers(prev => prev.map(m => m.id === editModal.id ? toEmployee(dto) : m));
      setEditModal(null);
      showToast("직원 정보가 수정되었습니다.");
    } catch (err: any) {
      showToast(err.message || "수정에 실패했습니다.", "error");
    } finally {
      setEditing(false);
    }
  };

  const handlePasswordReset = async (id: string, name: string) => {
    setProcessingId(id);
    setOpenMenuId(null);
    try {
      await apiFetch(`/api/users/${id}/password-reset/`, { method: "POST" });
      showToast(`${name}님의 비밀번호가 1111로 초기화되었습니다.`);
    } catch (err: any) {
      showToast(err.message || "초기화 실패", "error");
    } finally {
      setProcessingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setProcessingId(deleteTarget.id);
    try {
      await apiFetch(`/api/users/${deleteTarget.id}/`, { method: "DELETE" });
      setMembers(prev => prev.filter(m => m.id !== deleteTarget.id));
      showToast(`${deleteTarget.name}님 계정이 삭제되었습니다.`);
    } catch (err: any) {
      showToast(err.message || "삭제 실패", "error");
    } finally {
      setProcessingId(null);
      setDeleteTarget(null);
    }
  };

  const handleRoleChange = async (id: string, roleCode: "ADMIN" | "EMPLOYEE") => {
    try {
      const dto = await apiFetch<any>(`/api/users/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ role_code: roleCode }),
      });
      setMembers(prev => prev.map(m => m.id === id ? toEmployee(dto) : m));
      showToast("역할이 변경되었습니다.");
    } catch (err: any) {
      // 예전엔 실패해도 아무 알림이 없었다 — select의 value가 member.role에 그대로 묶여있어
      // 상태가 안 바뀌었는데도 드롭다운은 방금 고른 값으로 남아있어, PM이 "바뀐 줄" 착각하는
      // 문제가 있었다(전체 점검에서 발견). 실패를 알리면 드롭다운이 실제 값(member.role)으로
      // 다시 그려진다(members 상태를 안 건드리므로).
      showToast(err.message || "역할 변경 실패", "error");
    }
  };

  const handleStatusChange = async (id: string, status: EmployeeStatus) => {
    try {
      const dto = await apiFetch<any>(`/api/users/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ status_code: status }),
      });
      setMembers(prev => prev.map(m => m.id === id ? toEmployee(dto) : m));
      showToast("계정 상태가 변경되었습니다.");
    } catch (err: any) {
      showToast(err.message || "계정 상태 변경 실패", "error");
    }
  };

  const handleAddEmployee = async () => {
    if (!newUsername.trim()) return;
    setAdding(true);
    try {
      const dto = await apiFetch<any>("/api/users/", {
        method: "POST",
        body: JSON.stringify({
          username: newUsername.trim(),
          last_name: newLastName.trim(),
          first_name: newFirstName.trim(),
          dept_code: newDept || null,
          position_code: newPosition || null,
          job_role_code: newJobRole || null,
          emp_no: newEmployeeNo.trim() || null,
          hire_date: newHireDate || null,
        }),
      });
      const employee = toEmployee(dto);
      setMembers(prev => [employee, ...prev]);
      setAddModal(false);
      setNewUsername(""); setNewLastName(""); setNewFirstName(""); setNewDept("");
      setNewEmployeeNo(""); setNewPosition(""); setNewJobRole(""); setNewHireDate("");
      showToast(`${employee.name}님 계정이 생성되었습니다. 초기 비밀번호: 1111`);
    } catch (err: any) {
      showToast(err.message || "생성 실패", "error");
    } finally {
      setAdding(false);
    }
  };

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
            placeholder="이름, 아이디, 부서, 사번으로 검색..."
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
                <th className="px-6 py-4 font-semibold">보유 기술 / 자격증</th>
                <th className="px-6 py-4 font-semibold whitespace-nowrap">입사일 /<br />퇴사일</th>
                <th className="px-6 py-4 font-semibold">역할</th>
                <th className="px-6 py-4 font-semibold">상태</th>
                {isPM && <th className="px-6 py-4 font-semibold text-center">설정</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr><td colSpan={7} className="py-16 text-center"><Loader2 className="w-6 h-6 animate-spin text-primary mx-auto" /></td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="py-16 text-center text-muted-foreground">검색 결과가 없습니다.</td></tr>
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
                          <p className="text-xs text-muted-foreground">{member.username}</p>
                          {member.phone && <p className="text-xs text-muted-foreground">{member.phone}</p>}
                        </div>
                      </div>
                    </td>

                    {/* Department / Position / Job Role */}
                    <td className="px-6 py-4 text-muted-foreground whitespace-nowrap">
                      <p>{member.deptName || "-"} {member.positionName ? `· ${member.positionName}` : ""}</p>
                      <p className="text-xs">{member.jobRoleName || "-"}{member.empNo ? ` · ${member.empNo}` : ""}</p>
                    </td>

                    {/* Skills + Certs (read-only) */}
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {member.skills.slice(0, 3).map((s, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-semibold">{s}</span>
                        ))}
                        {member.skills.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">+{member.skills.length - 3}</span>
                        )}
                        {member.certifications.slice(0, 2).map((c, i) => (
                          <span key={`c${i}`} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-semibold">{c}</span>
                        ))}
                        {member.skills.length === 0 && member.certifications.length === 0 && (
                          <span className="text-xs text-muted-foreground">-</span>
                        )}
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
                          value={member.role === "PM" ? "ADMIN" : "EMPLOYEE"}
                          onChange={e => handleRoleChange(member.id, e.target.value as "ADMIN" | "EMPLOYEE")}
                          className={cn(
                            "appearance-none bg-transparent border rounded-lg px-3 py-1.5 text-xs font-semibold cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/40",
                            member.role === "PM" ? "text-emerald-400 border-emerald-400/30" : "text-muted-foreground border-border"
                          )}
                        >
                          <option value="ADMIN">PM</option>
                          <option value="EMPLOYEE">일반 멤버</option>
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
                          onChange={e => handleStatusChange(member.id, e.target.value as EmployeeStatus)}
                          className={cn(
                            "appearance-none bg-transparent border rounded-lg px-3 py-1.5 text-xs font-semibold cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/40",
                            STATUS_META[member.status].selectClass
                          )}
                        >
                          {statusOptions.map(s => (
                            <option key={s.code_id} value={s.code_id}>{STATUS_META[s.code_id]?.label ?? s.code_name}</option>
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
                                    id: member.id, lastName: member.lastName, firstName: member.firstName,
                                    department: member.deptCode || "", roleCode: member.roleCode || "EMPLOYEE",
                                    phone: member.phone || "", employeeNo: member.empNo || "",
                                    position: member.positionCode || "", jobRole: member.jobRoleCode || "",
                                    status: member.status, hireDate: member.hireDate ? member.hireDate.slice(0, 10) : "",
                                    resignDate: member.resignDate ? member.resignDate.slice(0, 10) : "",
                                    pastProjects: member.pastProjects,
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
      <div className="grid md:grid-cols-2 gap-4 mt-8">
        {[
          { role: "PM", color: "border-t-emerald-500", textColor: "text-emerald-500", perms: ["프로젝트 생성/삭제", "직원 추가 및 역할 변경", "비밀번호 초기화", "승인 및 반려 처리"] },
          { role: "일반 멤버", color: "border-t-primary", textColor: "text-primary", perms: ["할 일 생성 및 수정", "칸반 보드 상태 변경", "검토 요청", "본인 프로필 수정"] },
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
                <input
                  type="text"
                  placeholder="로그인에 사용할 아이디"
                  value={newUsername}
                  onChange={e => setNewUsername(e.target.value)}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  onKeyDown={e => e.key === "Enter" && handleAddEmployee()}
                />
                <p className="text-xs text-muted-foreground mt-1">초기 비밀번호: <strong>1111</strong></p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">성</label>
                  <input
                    type="text"
                    placeholder="홍"
                    value={newLastName}
                    onChange={e => setNewLastName(e.target.value)}
                    className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">이름</label>
                  <input
                    type="text"
                    placeholder="길동"
                    value={newFirstName}
                    onChange={e => setNewFirstName(e.target.value)}
                    className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
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
                    {deptOptions.map(d => <option key={d.code_id} value={d.code_id}>{d.code_name}</option>)}
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
                    {positionOptions.map(p => <option key={p.code_id} value={p.code_id}>{p.code_name}</option>)}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">직무 (선택)</label>
                  <select
                    value={newJobRole}
                    onChange={e => setNewJobRole(e.target.value)}
                    className="w-full px-3 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                  >
                    <option value="">선택 안 함</option>
                    {jobRoleOptions.map(j => <option key={j.code_id} value={j.code_id}>{j.code_name}</option>)}
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
              실제로는 계정이 비활성화·퇴사 처리되며, 이 작업은 목록 화면에서 되돌릴 수 없습니다.
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

      {/* Edit Modal — 필드가 많아 세로로 나열하면 모달이 지나치게 길어지므로 좌(기본정보)/우(이력) 2단 레이아웃으로 분리 */}
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
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">성</label>
                    <input
                      type="text"
                      value={editModal.lastName}
                      onChange={e => setEditModal({ ...editModal, lastName: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">이름</label>
                    <input
                      type="text"
                      value={editModal.firstName}
                      onChange={e => setEditModal({ ...editModal, firstName: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  </div>
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
                      {deptOptions.map(d => <option key={d.code_id} value={d.code_id}>{d.code_name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">권한</label>
                    <select
                      value={editModal.roleCode}
                      onChange={e => setEditModal({ ...editModal, roleCode: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                    >
                      <option value="EMPLOYEE">일반 멤버</option>
                      <option value="ADMIN">PM</option>
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
                      {positionOptions.map(p => <option key={p.code_id} value={p.code_id}>{p.code_name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">직무</label>
                    <select
                      value={editModal.jobRole}
                      onChange={e => setEditModal({ ...editModal, jobRole: e.target.value })}
                      className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none"
                    >
                      <option value="">선택 안 함</option>
                      {jobRoleOptions.map(j => <option key={j.code_id} value={j.code_id}>{j.code_name}</option>)}
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
                      {statusOptions.map(s => <option key={s.code_id} value={s.code_id}>{STATUS_META[s.code_id]?.label ?? s.code_name}</option>)}
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

              {/* 우측: 기술스택/자격증(읽기 전용)/주요프로젝트/연락처 — 태그형 이력 정보 */}
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">
                    기술 스택 <span className="font-normal">(읽기 전용 — 본인이 프로필에서 등록)</span>
                  </label>
                  <div className="flex flex-wrap gap-1.5 min-h-[2.5rem] px-3 py-2 bg-black/5 dark:bg-white/5 border border-border rounded-xl">
                    {editModal.pastProjects.length === 0 && members.find(m => m.id === editModal.id)?.skills.length === 0 ? (
                      <span className="text-xs text-muted-foreground py-1">-</span>
                    ) : (
                      (members.find(m => m.id === editModal.id)?.skills ?? []).map((s, i) => (
                        <span key={i} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary font-semibold">{s}</span>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">
                    자격증 <span className="font-normal">(읽기 전용)</span>
                  </label>
                  <div className="flex flex-wrap gap-1.5 min-h-[2.5rem] px-3 py-2 bg-black/5 dark:bg-white/5 border border-border rounded-xl">
                    {(members.find(m => m.id === editModal.id)?.certifications ?? []).length === 0 ? (
                      <span className="text-xs text-muted-foreground py-1">-</span>
                    ) : (
                      (members.find(m => m.id === editModal.id)?.certifications ?? []).map((c, i) => (
                        <span key={i} className="text-xs px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 font-semibold">{c}</span>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-semibold mb-1.5 block text-muted-foreground">주요 프로젝트</label>
                  <TagAutocomplete
                    value={editModal.pastProjects}
                    onChange={pastProjects => setEditModal({ ...editModal, pastProjects })}
                    suggestions={PROJECT_SUGGESTIONS}
                    placeholder="입력 후 Enter로 추가"
                    allowCustom
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
                disabled={editing}
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
