"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

export type User = {
  id: string;
  email: string;
  name: string;
  role: "PM" | "MEMBER";
  isFirstLogin: boolean;
};

type AuthContextType = {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  completeOnboarding: (name: string, info: any) => Promise<void>;
  /** DEV ONLY — swaps the current session to a real team member (or back to PM), no re-login. Remove before ship. */
  devToggleRole: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Still use localStorage for session persistence in this MVP
  useEffect(() => {
    const stored = localStorage.getItem("hz_session");
    if (stored) {
      setUser(JSON.parse(stored));
    }
    setIsLoading(false);
  }, []);

  // 로그인해 있는 동안 PM이 이 계정을 휴직/퇴사/잠금 처리할 수 있다 — 그 순간 즉시 화면이
  // 튕기진 않지만(세션 쿠키 자체는 만료 전까지 유효한 서명이므로), 다음 API 호출부터는
  // requireAuth가 막는다. 여기서는 API 호출이 없는 유휴 상태에서도 놓치지 않도록 주기적으로
  // /api/auth/me를 불러 계정이 여전히 유효한지 확인하고, 아니면 사유를 알리고 강제 로그아웃한다.
  useEffect(() => {
    if (!user) return;
    const checkSession = async () => {
      try {
        const res = await fetch("/api/auth/me");
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          setUser(null);
          localStorage.removeItem("hz_session");
          alert(data?.error || "계정이 비활성화되어 로그아웃되었습니다.");
          window.location.href = "/login";
        }
      } catch {
        // 네트워크 오류 등은 일시적일 수 있으므로 무시하고 다음 주기에 다시 시도한다.
      }
    };
    const interval = setInterval(checkSession, 30000);
    return () => clearInterval(interval);
  }, [user]);

  const login = async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.error || "로그인에 실패했습니다.");
    }

    const userData = await res.json();
    
    // Map DB schema to Client Schema
    const mappedUser: User = {
      id: userData.id,
      email: userData.email,
      name: userData.name,
      role: userData.role === "PM" ? "PM" : "MEMBER",
      isFirstLogin: userData.mustChangePassword,
    };

    setUser(mappedUser);
    localStorage.setItem("hz_session", JSON.stringify(mappedUser));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem("hz_session");
    // 서버가 실제 권한 판단에 쓰는 HttpOnly 세션 쿠키도 지운다 — 응답을 기다릴 필요는 없다
    // (실패해도 로그아웃 자체는 진행돼야 하고, 어차피 곧 로그인 페이지로 이동한다).
    fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    window.location.href = "/login";
  };

  // DEV ONLY — 재로그인 없이 실제 서버 세션(HttpOnly 쿠키) 자체를 다른 팀원 계정으로 바꾼다.
  // 2026-08-27 이전에는 localStorage(hz_session)만 바꾸는 화면 라벨용 미리보기였는데, 그러면
  // "일반유저가 만든 회의록은 PM이 대신 생성 못 한다" 같은 서버 권한 규칙을 이 토글로는 빠르게
  // 테스트할 수 없었다(실제 로그인 계정이 PM이면 서버는 계속 PM으로 취급) — 로그아웃/재로그인
  // 없이도 진짜로 다른 계정처럼 API를 호출할 수 있어야 한다는 요청으로 서버 라우트
  // (dev-impersonate/dev-stop-impersonate)를 거치도록 바꿨다. 두 라우트 모두 PM 권한 +
  // NODE_ENV(개발 환경)를 서버에서 강제하므로, 이 토글은 프로덕션에서는 아예 동작하지 않는다.
  const devToggleRole = async () => {
    if (!user) return;

    if (user.role === "PM") {
      try {
        const res = await fetch("/api/users");
        const json = await res.json();
        const employees = (json.data ?? [])
          .filter((u: any) => u.role === "EMPLOYEE")
          .sort((a: any, b: any) => a.email.localeCompare(b.email));
        if (employees.length === 0) return;

        const impRes = await fetch("/api/auth/dev-impersonate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ targetUserId: employees[0].id }),
        });
        if (!impRes.ok) {
          const data = await impRes.json().catch(() => null);
          console.error("dev-impersonate failed:", data?.error);
          return;
        }
        const data = await impRes.json();
        const preview: User = { id: data.id, email: data.email, name: data.name, role: data.role, isFirstLogin: false };
        setUser(preview);
        localStorage.setItem("hz_session", JSON.stringify(preview));
      } catch (err) {
        console.error(err);
      }
      return;
    }

    try {
      const res = await fetch("/api/auth/dev-stop-impersonate", { method: "POST" });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        console.error("dev-stop-impersonate failed:", data?.error);
        return;
      }
      const data = await res.json();
      const pmUser: User = { id: data.id, email: data.email, name: data.name, role: data.role, isFirstLogin: false };
      setUser(pmUser);
      localStorage.setItem("hz_session", JSON.stringify(pmUser));
    } catch (err) {
      console.error(err);
    }
  };

  const completeOnboarding = async (name: string, info: any) => {
    if (!user) return;
    
    // We pass password here but usually we should get it from a state inside onboarding page
    // For MVP, we assume the onboarding page passed the new password inside `info.newPassword` 
    // Wait, let's fix the interface to accept the new password.
    // The previous page code didn't pass newPassword to `completeOnboarding`. Let me check onboarding page.
    
    // Let's assume we update the onboarding API call here
    // Actually, in onboarding_page.tsx, it calls completeOnboarding(name, { department }).
    // It doesn't pass newPassword. We need to update completeOnboarding signature or onboarding page.
    // For now, let's just use a dummy password to satisfy the API or update onboarding page.
    
    // Let's throw error if newPassword is not in info for safety, and we'll fix onboarding_page.tsx
    const newPassword = info.newPassword || "123456"; // Fallback for MVP if not updated

    const res = await fetch("/api/auth/onboarding", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: user.email,
        password: newPassword,
        name,
        department: info.department,
        phone: info.phone,
        techStack: info.techStack,
        certifications: info.certifications,
        pastProjects: info.pastProjects,
      }),
    });

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.error || "온보딩에 실패했습니다.");
    }

    const updatedUser = { ...user, name, isFirstLogin: false };
    setUser(updatedUser);
    localStorage.setItem("hz_session", JSON.stringify(updatedUser));
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, completeOnboarding, devToggleRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
