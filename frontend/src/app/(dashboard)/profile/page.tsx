"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api/client";
import { Mail, Shield, KeyRound, Loader2, CheckCircle2, X, Phone, Pencil } from "lucide-react";
import { cn } from "@/lib/utils";
import { PROJECT_SUGGESTIONS } from "@/lib/employeeOptions";
import TagAutocomplete from "@/components/ui/TagAutocomplete";

const toList = (s: string) => (s ? s.split(",").map(v => v.trim()).filter(Boolean) : []);

// 2026-09-16: 기술 스택/자격증을 본인이 직접 추가/삭제할 수 있게 됐다 — 예전엔 이
// 값들을 저장하는 API 자체가 없어서(온보딩 화면 주석에 남아있던 사실) 세 화면
// (온보딩/프로필/직원관리)이 서로 "다른 데서 관리한다"고 미루기만 했었다.
type SkillEntry = { skill_id: number; skill_code: string; skill_name: string; proficiency_level: number };
type CertEntry = { cert_id: number; cert_code: string; cert_name: string };
type CodeOption = { code_id: string; code_name: string };

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
  const [infoLoading, setInfoLoading] = useState(true);
  const [phone, setPhone] = useState("");
  const [skills, setSkills] = useState<SkillEntry[]>([]);
  const [certifications, setCertifications] = useState<CertEntry[]>([]);
  const [pastProjects, setPastProjects] = useState<string[]>([]);
  const [savingInfo, setSavingInfo] = useState(false);

  // 추가 가능한 스킬/자격증 코드 목록(공통코드) + 지금 고른 값 + 처리 중 여부
  const [skillOptions, setSkillOptions] = useState<CodeOption[]>([]);
  const [certOptions, setCertOptions] = useState<CodeOption[]>([]);
  const [selectedSkillCode, setSelectedSkillCode] = useState("");
  const [selectedCertCode, setSelectedCertCode] = useState("");
  const [addingSkill, setAddingSkill] = useState(false);
  const [addingCert, setAddingCert] = useState(false);

  useEffect(() => {
    if (!user) return;
    apiFetch<any>("/api/users/me/")
      .then(data => {
        setPhone(data.phone || "");
        setSkills((data.skills ?? []).map((s: any) => ({
          skill_id: s.skill_id, skill_code: s.skill_code, skill_name: s.skill_name, proficiency_level: s.proficiency_level,
        })));
        setCertifications((data.certifications ?? []).map((c: any) => ({
          cert_id: c.cert_id, cert_code: c.cert_code, cert_name: c.cert_name,
        })));
        setPastProjects(toList(data.past_projects || ""));
      })
      .catch(() => showToast("내 정보를 불러오지 못했습니다.", "error"))
      .finally(() => setInfoLoading(false));
    apiFetch<any[]>("/api/common/codes/?group_prefix=SKILL")
      .then(list => setSkillOptions(list.map(c => ({ code_id: c.code_id, code_name: c.code_name }))))
      .catch(() => {});
    apiFetch<any[]>("/api/common/codes/?group_prefix=CERTIFICATION")
      .then(list => setCertOptions(list.map(c => ({ code_id: c.code_id, code_name: c.code_name }))))
      .catch(() => {});
  }, [user]);

  const handleAddSkill = async () => {
    if (!selectedSkillCode) return;
    setAddingSkill(true);
    try {
      const created = await apiFetch<any>("/api/users/me/skills/", {
        method: "POST",
        body: JSON.stringify({ skill_code: selectedSkillCode, proficiency_level: 3 }),
      });
      setSkills(prev => {
        const rest = prev.filter(s => s.skill_id !== created.skill_id);
        return [...rest, created];
      });
      setSelectedSkillCode("");
    } catch (err: any) {
      showToast(err.message || "기술 스택 추가에 실패했습니다.", "error");
    } finally {
      setAddingSkill(false);
    }
  };

  const handleRemoveSkill = async (skillId: number) => {
    const prev = skills;
    setSkills(cur => cur.filter(s => s.skill_id !== skillId)); // 낙관적 업데이트
    try {
      await apiFetch(`/api/users/me/skills/${skillId}/`, { method: "DELETE" });
    } catch (err: any) {
      setSkills(prev); // 실패하면 되돌림
      showToast(err.message || "삭제에 실패했습니다.", "error");
    }
  };

  const handleAddCertification = async () => {
    if (!selectedCertCode) return;
    setAddingCert(true);
    try {
      const created = await apiFetch<any>("/api/users/me/certifications/", {
        method: "POST",
        body: JSON.stringify({ cert_code: selectedCertCode }),
      });
      setCertifications(prev => {
        const rest = prev.filter(c => c.cert_id !== created.cert_id);
        return [...rest, created];
      });
      setSelectedCertCode("");
    } catch (err: any) {
      showToast(err.message || "자격증 추가에 실패했습니다.", "error");
    } finally {
      setAddingCert(false);
    }
  };

  const handleRemoveCertification = async (certId: number) => {
    const prev = certifications;
    setCertifications(cur => cur.filter(c => c.cert_id !== certId));
    try {
      await apiFetch(`/api/users/me/certifications/${certId}/`, { method: "DELETE" });
    } catch (err: any) {
      setCertifications(prev);
      showToast(err.message || "삭제에 실패했습니다.", "error");
    }
  };

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
              {/* 2026-09-16: 기술 스택/자격증을 본인이 직접 추가/삭제할 수 있게 바꿨다 —
                  예전엔 이 값들을 저장하는 API 자체가 없어서(온보딩 화면 주석 참고)
                  읽기 전용으로만 보여줬었다. */}
              <div>
                <label className="block text-sm font-medium mb-1">기술 스택</label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {skills.length === 0 ? (
                    <span className="text-sm text-muted-foreground">등록된 기술 스택이 없습니다.</span>
                  ) : skills.map(s => (
                    <span key={s.skill_id} className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-black/5 dark:bg-white/5 text-xs font-medium">
                      {s.skill_name}
                      <button type="button" onClick={() => handleRemoveSkill(s.skill_id)} className="text-muted-foreground hover:text-red-400" aria-label={`${s.skill_name} 삭제`}>
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <select
                    value={selectedSkillCode}
                    onChange={e => setSelectedSkillCode(e.target.value)}
                    className="flex-1 px-3 py-2 bg-black/5 dark:bg-white/5 border border-border rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-primary/40"
                  >
                    <option value="">기술 스택 선택...</option>
                    {skillOptions
                      .filter(o => !skills.some(s => s.skill_code === o.code_id))
                      .map(o => <option key={o.code_id} value={o.code_id}>{o.code_name}</option>)}
                  </select>
                  <button
                    type="button"
                    onClick={handleAddSkill}
                    disabled={!selectedSkillCode || addingSkill}
                    className="px-3 py-2 rounded-lg bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 disabled:opacity-50 transition-colors"
                  >
                    {addingSkill ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "추가"}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">자격증</label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {certifications.length === 0 ? (
                    <span className="text-sm text-muted-foreground">등록된 자격증이 없습니다.</span>
                  ) : certifications.map(c => (
                    <span key={c.cert_id} className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-black/5 dark:bg-white/5 text-xs font-medium">
                      {c.cert_name}
                      <button type="button" onClick={() => handleRemoveCertification(c.cert_id)} className="text-muted-foreground hover:text-red-400" aria-label={`${c.cert_name} 삭제`}>
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <select
                    value={selectedCertCode}
                    onChange={e => setSelectedCertCode(e.target.value)}
                    className="flex-1 px-3 py-2 bg-black/5 dark:bg-white/5 border border-border rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-primary/40"
                  >
                    <option value="">자격증 선택...</option>
                    {certOptions
                      .filter(o => !certifications.some(c => c.cert_code === o.code_id))
                      .map(o => <option key={o.code_id} value={o.code_id}>{o.code_name}</option>)}
                  </select>
                  <button
                    type="button"
                    onClick={handleAddCertification}
                    disabled={!selectedCertCode || addingCert}
                    className="px-3 py-2 rounded-lg bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 disabled:opacity-50 transition-colors"
                  >
                    {addingCert ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "추가"}
                  </button>
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
