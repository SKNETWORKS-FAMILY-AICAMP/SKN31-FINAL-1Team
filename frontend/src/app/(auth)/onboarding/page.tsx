"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Loader2, KeyRound, User as UserIcon, Building, Sparkles, Phone, ArrowLeft, ArrowRight, Wrench, Award, X } from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type DeptOption = { code_id: string; code_name: string };

export default function OnboardingPage() {
  const { user, completeOnboarding, isLoading } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState<1 | 2>(1);

  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [deptCode, setDeptCode] = useState("");
  const [phone, setPhone] = useState("");

  // 부서 목록 — 예전엔 프론트에 하드코딩된 한글 이름 배열("개발팀" 등)을 그대로
  // 서버에 dept_code로 보냈는데, dept_code는 실제로 CommonCode(USER_DEPARTMENT
  // 그룹)의 code_id(예: "DEPT_DEV")를 받는 외래키라 절대 저장될 수 없었다
  // (직원관리 화면의 "직원 추가" 모달은 이미 이 API로 정상 동작하고 있어서
  // 그 패턴을 그대로 따른다).
  const [deptOptions, setDeptOptions] = useState<DeptOption[]>([]);

  // 2026-09-16: 기술 스택/자격증 저장 API(/api/users/me/skills/, /api/users/me/certifications/)가
  // 새로 생겨서 온보딩에도 다시 넣는다 — 이전엔 저장할 곳이 없어 아예 뺐었다(아래 handleSubmit
  // 주석 참고). 이 화면은 "다음/이전"으로 넘나드는 마법사 형태라 다른 필드(부서/연락처)처럼
  // 최종 제출 시점에만 실제로 저장한다 — 선택은 여기서 로컬 상태로만 들고 있는다.
  const [skillOptions, setSkillOptions] = useState<DeptOption[]>([]);
  const [certOptions, setCertOptions] = useState<DeptOption[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<DeptOption[]>([]);
  const [selectedCerts, setSelectedCerts] = useState<DeptOption[]>([]);
  const [pendingSkillCode, setPendingSkillCode] = useState("");
  const [pendingCertCode, setPendingCertCode] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<DeptOption[]>("/api/common/codes/?group_code=USER_DEPARTMENT")
      .then(setDeptOptions)
      .catch(() => {}); // 부서는 선택 항목이라 조회 실패해도 온보딩 자체를 막지 않음
    apiFetch<DeptOption[]>("/api/common/codes/?group_prefix=SKILL").then(setSkillOptions).catch(() => {});
    apiFetch<DeptOption[]>("/api/common/codes/?group_prefix=CERTIFICATION").then(setCertOptions).catch(() => {});
  }, []);

  const addSkill = () => {
    if (!pendingSkillCode) return;
    const opt = skillOptions.find(o => o.code_id === pendingSkillCode);
    if (opt && !selectedSkills.some(s => s.code_id === opt.code_id)) {
      setSelectedSkills(prev => [...prev, opt]);
    }
    setPendingSkillCode("");
  };
  const removeSkill = (codeId: string) => setSelectedSkills(prev => prev.filter(s => s.code_id !== codeId));

  const addCert = () => {
    if (!pendingCertCode) return;
    const opt = certOptions.find(o => o.code_id === pendingCertCode);
    if (opt && !selectedCerts.some(c => c.code_id === opt.code_id)) {
      setSelectedCerts(prev => [...prev, opt]);
    }
    setPendingCertCode("");
  };
  const removeCert = (codeId: string) => setSelectedCerts(prev => prev.filter(c => c.code_id !== codeId));

  // Guard
  useEffect(() => {
    if (!isLoading) {
      if (!user) router.push("/login");
      else if (!user.isFirstLogin) router.push("/");
    }
  }, [user, isLoading, router]);

  const handleNext = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (newPassword !== confirmPassword) {
      return setError("비밀번호가 일치하지 않습니다.");
    }
    if (newPassword.length < 6) {
      return setError("새 비밀번호는 최소 6자리 이상이어야 합니다.");
    }
    setStep(2);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!lastName.trim() || !firstName.trim()) {
      return setError("성과 이름을 모두 입력해주세요.");
    }

    setLoading(true);
    try {
      await completeOnboarding(`${lastName.trim()}${firstName.trim()}`, {
        lastName: lastName.trim(),
        firstName: firstName.trim(),
        newPassword,
        phone,
        deptCode,
      });
      // 2026-09-16: 기술 스택/자격증은 온보딩 성공 뒤 best-effort로 저장한다 —
      // 전용 API가 완료 처리(is_onboarded)와 별개 엔드포인트라, 여기서 실패해도
      // 온보딩 자체(비밀번호 변경, 이름/부서 등록)를 막지 않는다. 실패한 항목은
      // 나중에 프로필 화면에서 다시 추가하면 된다.
      await Promise.allSettled([
        ...selectedSkills.map(s => apiFetch("/api/users/me/skills/", {
          method: "POST",
          body: JSON.stringify({ skill_code: s.code_id, proficiency_level: 3 }),
        })),
        ...selectedCerts.map(c => apiFetch("/api/users/me/certifications/", {
          method: "POST",
          body: JSON.stringify({ cert_code: c.code_id }),
        })),
      ]);
      router.push("/");
    } catch (err: any) {
      setError(err.message);
      setLoading(false);
    }
  };

  if (isLoading || !user || !user.isFirstLogin) {
    return <div className="min-h-screen flex items-center justify-center">로딩 중...</div>;
  }

  return (
    <div className="sm:mx-auto sm:w-full sm:max-w-md">
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <Sparkles className="w-8 h-8 text-primary" />
        </div>
        <h2 className="text-3xl font-extrabold tracking-tight">환영합니다!</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {step === 1 ? <>보안을 위해 비밀번호를 먼저 변경해주세요.</> : <>이제 기본 프로필을 완성해주세요.</>}
        </p>
        <div className="flex items-center justify-center gap-2 mt-4">
          <div className={cn("h-1.5 w-10 rounded-full transition-colors", step >= 1 ? "bg-primary" : "bg-black/10 dark:bg-white/10")} />
          <div className={cn("h-1.5 w-10 rounded-full transition-colors", step >= 2 ? "bg-primary" : "bg-black/10 dark:bg-white/10")} />
        </div>
      </div>

      <div className="glass py-8 px-4 shadow sm:rounded-2xl sm:px-10 border border-border relative overflow-hidden">
        {error && (
          <div className="p-3 mb-5 rounded-lg bg-red-500/10 text-red-500 text-sm">
            {error}
          </div>
        )}

        {step === 1 ? (
          <form className="space-y-5" onSubmit={handleNext}>
            <div>
              <label className="block text-sm font-medium mb-1">새 비밀번호 (필수)</label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-3 h-5 w-5 text-muted-foreground" />
                <input
                  type="password"
                  required
                  className="w-full pl-10 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm"
                  placeholder="보안을 위해 강력한 비밀번호 설정"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">새 비밀번호 확인 (필수)</label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-3 h-5 w-5 text-muted-foreground" />
                <input
                  type="password"
                  required
                  className="w-full pl-10 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm"
                  placeholder="비밀번호 다시 입력"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                className="w-full flex items-center justify-center gap-2 py-3 px-4 border border-transparent rounded-xl shadow-sm text-sm font-bold text-white bg-primary hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors"
              >
                다음 <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>
        ) : (
          <form className="space-y-5" onSubmit={handleSubmit}>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">성 (필수)</label>
                <div className="relative">
                  <UserIcon className="absolute left-3 top-3 h-5 w-5 text-muted-foreground" />
                  <input
                    type="text"
                    required
                    className="w-full pl-10 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm"
                    placeholder="홍"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">이름 (필수)</label>
                <input
                  type="text"
                  required
                  className="w-full bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 px-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm"
                  placeholder="길동"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">소속 부서 (선택)</label>
              <div className="relative">
                <Building className="absolute left-3 top-3 h-5 w-5 text-muted-foreground pointer-events-none" />
                <select
                  className="w-full pl-10 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm appearance-none"
                  value={deptCode}
                  onChange={(e) => setDeptCode(e.target.value)}
                >
                  <option value="">선택 안 함</option>
                  {deptOptions.map(d => <option key={d.code_id} value={d.code_id}>{d.code_name}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">연락처 (선택)</label>
              <div className="relative">
                <Phone className="absolute left-3 top-3 h-5 w-5 text-muted-foreground" />
                <input
                  type="text"
                  className="w-full pl-10 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm"
                  placeholder="010-0000-0000"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 flex items-center gap-1.5"><Wrench className="w-3.5 h-3.5" /> 기술 스택 (선택)</label>
              {selectedSkills.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {selectedSkills.map(s => (
                    <span key={s.code_id} className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-black/5 dark:bg-white/5 text-xs font-medium">
                      {s.code_name}
                      <button type="button" onClick={() => removeSkill(s.code_id)} className="text-muted-foreground hover:text-red-400" aria-label={`${s.code_name} 삭제`}>
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex gap-1.5">
                <select
                  value={pendingSkillCode}
                  onChange={(e) => setPendingSkillCode(e.target.value)}
                  className="flex-1 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-2.5 px-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm appearance-none"
                >
                  <option value="">기술 스택 선택...</option>
                  {skillOptions
                    .filter(o => !selectedSkills.some(s => s.code_id === o.code_id))
                    .map(o => <option key={o.code_id} value={o.code_id}>{o.code_name}</option>)}
                </select>
                <button
                  type="button"
                  onClick={addSkill}
                  disabled={!pendingSkillCode}
                  className="px-4 rounded-xl bg-primary/10 text-primary text-sm font-bold hover:bg-primary/20 disabled:opacity-50 transition-colors"
                >
                  추가
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1 flex items-center gap-1.5"><Award className="w-3.5 h-3.5" /> 자격증 (선택)</label>
              {selectedCerts.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {selectedCerts.map(c => (
                    <span key={c.code_id} className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-black/5 dark:bg-white/5 text-xs font-medium">
                      {c.code_name}
                      <button type="button" onClick={() => removeCert(c.code_id)} className="text-muted-foreground hover:text-red-400" aria-label={`${c.code_name} 삭제`}>
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex gap-1.5">
                <select
                  value={pendingCertCode}
                  onChange={(e) => setPendingCertCode(e.target.value)}
                  className="flex-1 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-2.5 px-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm appearance-none"
                >
                  <option value="">자격증 선택...</option>
                  {certOptions
                    .filter(o => !selectedCerts.some(c => c.code_id === o.code_id))
                    .map(o => <option key={o.code_id} value={o.code_id}>{o.code_name}</option>)}
                </select>
                <button
                  type="button"
                  onClick={addCert}
                  disabled={!pendingCertCode}
                  className="px-4 rounded-xl bg-primary/10 text-primary text-sm font-bold hover:bg-primary/20 disabled:opacity-50 transition-colors"
                >
                  추가
                </button>
              </div>
            </div>

            <div className="pt-2 flex gap-3">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="flex items-center justify-center gap-2 py-3 px-4 rounded-xl border border-border text-sm font-bold hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" /> 이전
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 flex justify-center py-3 px-4 border border-transparent rounded-xl shadow-sm text-sm font-bold text-white bg-primary hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 transition-colors"
              >
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : "프로필 완성 및 시작하기"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
