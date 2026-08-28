"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Loader2, User, Lock, ShieldAlert } from "lucide-react";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const fullEmail = `${userId}@heyzzabi.com`;
      await login(fullEmail, password);
      // 로그인 성공 시 대시보드(또는 온보딩)로 강제 이동
      router.push("/");
    } catch (err: any) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <div className="sm:mx-auto sm:w-full sm:max-w-md animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-extrabold tracking-tight">HeyZzabi 로그인</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          B2B 전용 계정입니다. 계정이 없다면 PM에게 문의하세요.
        </p>
      </div>

      <div className="glass py-8 px-4 shadow sm:rounded-2xl sm:px-10 border border-border relative overflow-hidden">
        {/* Decor */}
        <div className="absolute -top-10 -right-10 w-32 h-32 bg-primary/20 blur-3xl rounded-full pointer-events-none" />

        <form className="space-y-6 relative z-10" onSubmit={handleSubmit}>
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-sm flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium">사내 아이디 (ID)</label>
            <div className="mt-1 relative rounded-md shadow-sm flex">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <User className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                type="text"
                required
                className="block w-full pl-10 pr-[130px] sm:text-sm bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none placeholder:text-muted-foreground"
                placeholder="아이디"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
              />
              <div className="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none">
                <span className="text-muted-foreground text-sm font-medium whitespace-nowrap">@heyzzabi.com</span>
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium">비밀번호</label>
            <div className="mt-1 relative rounded-md shadow-sm flex">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                type="password"
                required
                className="block w-full pl-10 sm:text-sm bg-black/5 dark:bg-white/5 border border-border rounded-xl py-3 focus:ring-2 focus:ring-primary/50 focus:outline-none placeholder:text-muted-foreground"
                placeholder="비밀번호"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading || !userId || !password}
              className="w-full flex justify-center py-3 px-4 border border-transparent rounded-xl shadow-sm text-sm font-bold text-white bg-primary hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 transition-colors"
            >
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : "로그인"}
            </button>
          </div>
        </form>

        <div className="mt-6 text-center text-xs text-muted-foreground bg-black/5 dark:bg-white/5 p-4 rounded-xl border border-border">
          <p className="font-bold mb-1 text-foreground">테스트 계정 안내</p>
          <p>PM (관리자): 아이디 <b>pm</b> / 비번 <b>admin</b></p>
          <p>MEMBER (신규): 아이디 <b>newbie</b> / 비번 <b>temp</b></p>
        </div>
      </div>
    </div>
  );
}
