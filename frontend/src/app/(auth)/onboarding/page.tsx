"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Loader2, KeyRound, User as UserIcon, Building, Sparkles, Phone, ArrowLeft, ArrowRight } from "lucide-react";
import TagAutocomplete from "@/components/ui/TagAutocomplete";
import { DEPARTMENTS, SKILL_SUGGESTIONS, CERT_SUGGESTIONS, PROJECT_SUGGESTIONS } from "@/lib/employeeOptions";
import { cn } from "@/lib/utils";

export default function OnboardingPage() {
  const { user, completeOnboarding, isLoading } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState<1 | 2>(1);

  const [name, setName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [department, setDepartment] = useState("");
  const [phone, setPhone] = useState("");
  const [techStack, setTechStack] = useState<string[]>([]);
  const [certifications, setCertifications] = useState<string[]>([]);
  const [pastProjects, setPastProjects] = useState<string[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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

    if (!name.trim()) {
      return setError("이름을 입력해주세요.");
    }

    setLoading(true);
    try {
      await completeOnboarding(name, {
        department,
        newPassword,
        phone,
        techStack: techStack.join(", "),
        certifications: certifications.join(", "),
        pastProjects: pastProjects.join(", "),
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
    <div className={cn("sm:mx-auto sm:w-full transition-all", step === 1 ? "sm:max-w-md" : "sm:max-w-2xl")}>
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
              {/* Left column: basic info */}
              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-medium mb-1">실명 (필수)</label>
                  <div className="relative">
                    <UserIcon className="absolute left-3 top-3 h-5 w-5 text-muted-foreground" />
                    <input
                      type="text"
                      required
                      className="w-full pl-10 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm"
                      placeholder="홍길동"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">소속 부서 (선택)</label>
                  <div className="relative">
                    <Building className="absolute left-3 top-3 h-5 w-5 text-muted-foreground pointer-events-none" />
                    <select
                      className="w-full pl-10 bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none text-sm appearance-none"
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                    >
                      <option value="">선택 안 함</option>
                      {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
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
              </div>

              {/* Right column: skills / career info */}
              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-medium mb-1">기술 스택 (선택)</label>
                  <TagAutocomplete value={techStack} onChange={setTechStack} suggestions={SKILL_SUGGESTIONS} placeholder="목록에서 선택" allowCustom={false} />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">자격증 (선택)</label>
                  <TagAutocomplete value={certifications} onChange={setCertifications} suggestions={CERT_SUGGESTIONS} placeholder="목록에서 선택" allowCustom={false} />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">주요 프로젝트 경험 (선택)</label>
                  <TagAutocomplete value={pastProjects} onChange={setPastProjects} suggestions={PROJECT_SUGGESTIONS} placeholder="목록에서 선택" allowCustom={false} />
                </div>
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
