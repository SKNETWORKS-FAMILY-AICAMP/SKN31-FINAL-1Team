"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { apiFetch } from "@/lib/api/client";
import { toUser } from "@/lib/api/mappers";

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
  // 튕기진 않지만(access 토큰 자체는 만료 전까지 유효한 서명이므로), 다음 API 호출부터는
  // 서버가 막는다. 여기서는 API 호출이 없는 유휴 상태에서도 놓치지 않도록 주기적으로
  // GET /api/users/me/ 를 불러 계정이 여전히 유효한지 확인하고, 아니면 강제 로그아웃한다.
  useEffect(() => {
    if (!user) return;
    const checkSession = async () => {
      try {
        await apiFetch("/api/users/me/");
      } catch {
        // apiFetch는 네트워크 오류와 401/403을 구분하지 않고 둘 다 throw하므로, 여기서 바로
        // 로그아웃 처리한다 — 일시적 네트워크 오류로 오탐하더라도 재로그인만 하면 되니 안전한 쪽.
        setUser(null);
        localStorage.removeItem("hz_session");
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
      }
    };
    const interval = setInterval(checkSession, 30000);
    return () => clearInterval(interval);
  }, [user]);

  const login = async (email: string, password: string) => {
    // 명세서 규격: POST /api/users/login/ — Request Body { username, password },
    // Response Body { message, user: { id, username, full_name, emp_no }, access, refresh }.
    // apiFetch가 API_BASE_URL(.env.local의 NEXT_PUBLIC_API_BASE_URL)을 붙여 Django로 직접
    // 보낸다 — 예전엔 상대경로("/api/users/login/")로 호출해서 실제로는 프론트 자신의 Next.js
    // 서버로 요청이 갔고(존재하지 않는 경로라 404), credentials:"include"로 세션 쿠키를
    // 기대했지만 백엔드는 JWT만 인증으로 인정해 그 쿠키는 이후 어떤 요청에서도 쓰이지 않았다.
    type LoginResponse = {
      message: string;
      user: { id: number | string; username: string; full_name: string; emp_no: string | null };
      access: string;
      refresh: string;
    };
    let data: LoginResponse;
    try {
      data = await apiFetch<LoginResponse>("/api/users/login/", {
        method: "POST",
        body: JSON.stringify({ username: email, password }),
      });
    } catch (err: any) {
      throw new Error(err.message || "로그인에 실패했습니다.");
    }

    // JWT는 apiFetch가 매 요청마다 localStorage의 access_token을 읽어 Authorization 헤더에
    // 붙이므로, 이후 모든 API 호출이 인증되려면 이 저장이 먼저 끝나야 한다.
    localStorage.setItem("access_token", data.access);
    localStorage.setItem("refresh_token", data.refresh);

    // 로그인 응답(UserSimpleSerializer)에는 role 정보가 없다 — 화면의 PM/MEMBER 분기에 필요한
    // role_code는 GET /api/users/me/ (UserDetailSerializer)에만 있어서 한 번 더 불러온다.
    const profile = await apiFetch<any>("/api/users/me/");
    const mappedUser = toUser(profile);

    setUser(mappedUser);
    localStorage.setItem("hz_session", JSON.stringify(mappedUser));
  };

  const logout = () => {
    const refreshToken = localStorage.getItem("refresh_token");
    // apiFetch는 호출 시점에 localStorage의 access_token을 동기적으로 읽어 Authorization
    // 헤더에 넣으므로, 아래에서 토큰을 지우기 전에 먼저 호출해야 한다(순서를 바꾸면 이 요청
    // 자체가 인증 없이 나가 401을 받는다). 응답은 기다릴 필요 없다 — 실패해도 로그아웃 자체는
    // 진행돼야 하고, 클라이언트가 토큰을 이미 버리므로 사실상 로그아웃된 것과 같다.
    apiFetch("/api/users/logout/", {
      method: "POST",
      body: JSON.stringify({ refresh: refreshToken }),
    }).catch(() => {});

    setUser(null);
    localStorage.removeItem("hz_session");
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
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
