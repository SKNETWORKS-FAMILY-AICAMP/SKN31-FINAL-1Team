"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import { User as UserIcon, Mail, Shield, KeyRound, Loader2, CheckCircle2, X, Phone, Pencil } from "lucide-react";
import { cn } from "@/lib/utils";
import { PROJECT_SUGGESTIONS } from "@/lib/employeeOptions";
import TagAutocomplete from "@/components/ui/TagAutocomplete";

const toList = (s: string) => (s ? s.split(",").map(v => v.trim()).filter(Boolean) : []);

export default function ProfilePage() {
  const { user } = useAuth();

  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  // 2026-09-01: PATCH /api/users/me/change-password/ 신규 추가 — 이전엔 PM 초기화만 가능했다.
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);

  // 내 정보 (온보딩 때 입력한 항목들 — 언제든 수정 가능해야 함)
  // 기술 스택/자격증은 Django에서 CommonCode를 참조하는 구조화된 데이터(UserSkill/UserCertification)라
  // 여기서 자유 텍스트로 바로 수정할 수 없다 — 직원관리(members) 화면과 동일하게 읽기 전용으로만 보여준다.
  const [infoLoading, setInfoLoading] = useState(true);
  const [phone, setPhone] = useState("");
  const [techStack, setTechStack] = useState<string[]>([]);
  const [certifications, setCertifications] = useState<string[]>([]);
  const [pastProjects, setPastProjects] = useState<string[]>([]);
  const [savingInfo, setSavingInfo] = useState(false);

  useEffect(() => {
    if (!user) return;
    apiFetch<any>("/api/users/me/")
      .then(data => {
        setPhone(data.phone || "");
        setTechStack((data.skills ?? []).map((s: any) => s.skill_name));
        setCertifications((data.certifications ?? []).map((c: any) => c.cert_name));
        setPastProjects(toList(data.past_projects || ""));
      })
      .catch(() => showToast("내 정보를 불러오지 못했습니다.", "error"))
      .finally(() => setInfoLoading(false));
  }, [user]);

  const showToast = (msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const closePasswordModal = () => {
    setPasswordModalOpen(false);
    setPasswordError("");
    setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    if (newPassword !== confirmPassword) {
      setPasswordError("새 비밀번호가 일치하지 않습니다.");
      return;
    }
    setChangingPassword(true);
    try {
      await apiFetch("/api/users/me/change-password/", {
        method: "PATCH",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      closePasswordModal();
      showToast("비밀번호가 변경되었습니다.");
    } catch (err: any) {
      setPasswordError(err.message || "비밀번호 변경에 실패했습니다.");
    } finally {
      setChangingPassword(false);
    }
  };

  const handleSaveInfo = async () => {
    if (!user) return;
    setSavingInfo(true);
    try {
      await apiFetch(`/api/users/${user.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          phone,
          past_projects: pastProjects.join(", "),
        }),
      });
      showToast("내 정보가 저장되었습니다.");
    } catch (err: any) {
      showToast(err.message || "저장에 실패했습니다.", "error");
    } finally {
      setSavingInfo(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
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

      <div>
        <h1 className="text-2xl font-bold tracking-tight">프로필</h1>
        <p className="text-muted-foreground text-sm mt-1">내 계정 정보를 확인합니다.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* 좌측: 이름 · 이메일 · 권한 + 비밀번호 변경 */}
        <div className="glass rounded-2xl border border-border shadow-sm p-6 space-y-5">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-primary/15 text-primary flex items-center justify-center text-xl font-bold shrink-0">
              {user?.name?.charAt(0) ?? "?"}
            </div>
            <div>
              <p className="text-lg font-bold">{user?.name ?? "이름 없음"}</p>
              <p className="text-sm text-muted-foreground">{user?.role === "PM" ? "관리자 · Project Manager" : "일반 팀원"}</p>
            </div>
          </div>

          <div className="divide-y divide-border border-t border-border pt-2">
            <div className="flex items-center gap-3 py-3 text-sm">
              <Mail className="w-4 h-4 text-muted-foreground shrink-0" />
              <span className="text-muted-foreground w-20">이메일</span>
              <span className="font-medium">{user?.email ?? "-"}</span>
            </div>
            <div className="flex items-center gap-3 py-3 text-sm">
              <Shield className="w-4 h-4 text-muted-foreground shrink-0" />
              <span className="text-muted-foreground w-20">권한</span>
              <span className="font-medium">{user?.role ?? "-"}</span>
            </div>
          </div>

          <button
            onClick={() => setPasswordModalOpen(true)}
            className="w-full flex justify-center items-center gap-2 py-2.5 rounded-xl border border-border hover:bg-black/5 dark:hover:bg-white/5 text-sm font-bold transition-colors"
          >
            <KeyRound className="w-4 h-4 text-primary" /> 비밀번호 변경
          </button>
        </div>

        {/* 우측: 내 정보 수정 */}
        <div className="glass rounded-2xl border border-border shadow-sm p-6 space-y-4">
          <h2 className="font-bold flex items-center gap-2">
            <Pencil className="w-4 h-4 text-primary" /> 내 정보 수정
          </h2>

          {infoLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <Loader2 className="w-4 h-4 animate-spin" /> 불러오는 중...
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1 flex items-center gap-1.5"><Phone className="w-3.5 h-3.5" /> 연락처</label>
                <input
                  type="text"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="010-0000-0000"
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              {/* 기술 스택/자격증은 직원관리 화면에서 PM이 관리하는 구조화된 데이터라 여기서는
                  읽기 전용으로만 보여준다(members/page.tsx와 동일한 처리). */}
              <div>
                <label className="block text-sm font-medium mb-1">기술 스택</label>
                <div className="flex flex-wrap gap-1.5">
                  {techStack.length === 0 ? (
                    <span className="text-sm text-muted-foreground">등록된 기술 스택이 없습니다.</span>
                  ) : techStack.map((s, i) => (
                    <span key={i} className="px-2.5 py-1 rounded-lg bg-black/5 dark:bg-white/5 text-xs font-medium">{s}</span>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">자격증</label>
                <div className="flex flex-wrap gap-1.5">
                  {certifications.length === 0 ? (
                    <span className="text-sm text-muted-foreground">등록된 자격증이 없습니다.</span>
                  ) : certifications.map((c, i) => (
                    <span key={i} className="px-2.5 py-1 rounded-lg bg-black/5 dark:bg-white/5 text-xs font-medium">{c}</span>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">주요 프로젝트 경험</label>
                <TagAutocomplete value={pastProjects} onChange={setPastProjects} suggestions={PROJECT_SUGGESTIONS} placeholder="목록에서 선택" allowCustom={false} />
              </div>
              <button
                onClick={handleSaveInfo}
                disabled={savingInfo}
                className="w-full flex justify-center items-center gap-2 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {savingInfo ? <Loader2 className="w-4 h-4 animate-spin" /> : "내 정보 저장"}
              </button>
            </div>
          )}
        </div>
      </div>

      {passwordModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-primary" /> 비밀번호 변경
              </h3>
              <button onClick={closePasswordModal} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"><X className="w-4 h-4" /></button>
            </div>

            {passwordError && (
              <div className="p-3 mb-4 rounded-lg bg-red-500/10 text-red-500 text-sm">{passwordError}</div>
            )}

            <form className="space-y-4" onSubmit={handleChangePassword}>
              <div>
                <label className="block text-sm font-medium mb-1">현재 비밀번호</label>
                <input
                  type="password"
                  required
                  autoFocus
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">새 비밀번호</label>
                <input
                  type="password"
                  required
                  minLength={4}
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">새 비밀번호 확인</label>
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={closePasswordModal} className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5">취소</button>
                <button
                  type="submit"
                  disabled={changingPassword}
                  className="flex-1 flex justify-center items-center gap-2 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {changingPassword ? <Loader2 className="w-4 h-4 animate-spin" /> : "변경하기"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
