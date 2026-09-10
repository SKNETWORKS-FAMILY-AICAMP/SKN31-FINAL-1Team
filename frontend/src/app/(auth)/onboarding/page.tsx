"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Loader2, KeyRound, User as UserIcon, Building, Sparkles, Phone, ArrowLeft, ArrowRight } from "lucide-react";
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

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<DeptOption[]>("/api/common/codes/?group_code=USER_DEPARTMENT")
      .then(setDeptOptions)
      .catch(() => {}); // 부서는 선택 항목이라 조회 실패해도 온보딩 자체를 막지 않음
  }, []);

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
            {/* 기술 스택/자격증/프로젝트 경험 입력은 뺐다 — 백엔드에 이 값들을 저장할
                API가 아직 없어서(User.skills/certifications는 UserDetailSerializer에서
                읽기 전용), 여기서 입력받아도 조용히 버려지고 있었다(실제로 확인). 입력을
                받는데 저장이 안 되는 것보다, 아예 안 받는 게 덜 혼란스럽다. 저장 API가
                추가되면 그때 다시 넣으면 된다. */}

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
