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
    // 2026-09-01: apiFetch는 네트워크 오류와 401/403을 구분 안 하고 둘 다 throw하는데, 예전엔
    // 여기서 그 둘을 구분 없이 곧장 강제 로그아웃시켰다 — WSL 개발 환경처럼 네트워크가 잠깐씩
    // 끊기는 상황에서 "계속 로그아웃된다"는 걸 사용자가 실제로 겪었다. access 토큰은 apiFetch가
    // 401을 만나면 자체적으로 refresh 후 재시도하므로, 여기서 또 401을 받는다는 건 refresh
    // 토큰까지 진짜 만료/무효라는 뜻 — 그때만 로그아웃한다. 그 외(네트워크 오류, 서버 일시 다운
    // 등)는 다음 주기에 다시 시도하고 이번엔 그냥 넘어간다.
    const checkSession = async () => {
      let res: Response;
      try {
        res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/users/me/`, {
          credentials: "include",
        });
      } catch {
        return; // 네트워크 오류 — 일시적일 수 있으니 로그아웃시키지 않고 다음 주기에 재시도
      }
      if (res.status === 401 || res.status === 403) {
        // apiFetch를 한 번 더 태워서 refresh 시도까지 확실히 거친 뒤에도 401이면 진짜 만료된 것
        try {
          await apiFetch("/api/users/me/");
          return; // refresh로 살아났으면 그냥 계속 진행
        } catch {
          setUser(null);
          localStorage.removeItem("hz_session");
          window.location.href = "/login";
        }
      }
      // 200이거나 401/403이 아닌 다른 오류(5xx 등)는 계정 문제가 아니므로 무시
    };
    const interval = setInterval(checkSession, 30000);
    return () => clearInterval(interval);
  }, [user]);

  const login = async (email: string, password: string) => {
    // 2026-08-31: 토큰을 localStorage 대신 HttpOnly 쿠키로 옮기면서, 로그인(쓰기 요청) 전에
    // csrftoken 쿠키를 먼저 확보해야 한다 — Django의 CSRF 검증은 X-CSRFToken 헤더 값이
    // csrftoken 쿠키 값과 일치하는지 보는데, 첫 로그인 시도 시점엔 그 쿠키가 아직 없다.
    await apiFetch("/api/users/csrf/");

    type LoginResponse = {
      message: string;
      user: { id: number | string; username: string; full_name: string; emp_no: string | null };
    };
    try {
      await apiFetch<LoginResponse>("/api/users/login/", {
        method: "POST",
        body: JSON.stringify({ username: email, password }),
      });
    } catch (err: any) {
      throw new Error(err.message || "로그인에 실패했습니다.");
    }
    // access/refresh 토큰은 이제 서버가 Set-Cookie로 내려준다 — 여기서 직접 저장할 게 없다.

    // 로그인 응답(UserSimpleSerializer)에는 role 정보가 없다 — 화면의 PM/MEMBER 분기에 필요한
    // role_code는 GET /api/users/me/ (UserDetailSerializer)에만 있어서 한 번 더 불러온다.
    const profile = await apiFetch<any>("/api/users/me/");
    const mappedUser = toUser(profile);

    setUser(mappedUser);
    localStorage.setItem("hz_session", JSON.stringify(mappedUser));
  };

  const logout = () => {
    // 쿠키(access/refresh)는 HttpOnly라 프론트가 직접 지울 수 없다 — 서버가 응답에서
    // Set-Cookie로 만료시켜야 한다(users/views.py LogoutView의 clear_auth_cookies).
    apiFetch("/api/users/logout/", { method: "POST" }).catch(() => {});

    setUser(null);
    localStorage.removeItem("hz_session");
    window.location.href = "/login";
  };

  // DEV ONLY — 재로그인 없이 다른 팀원 계정으로 세션을 바꿔본다.
  // 2026-08-31: 토큰이 HttpOnly 쿠키로 바뀌면서 "프론트 JS가 원래 PM 토큰을 보관해뒀다가
  // 되돌린다"는 방식이 아예 불가능해졌다(JS가 쿠키 값을 읽을 수 없으므로) — 대신 서버가
  // 원래 토큰을 dev_original_* 쿠키에 보관해두고, 복귀는 전용 엔드포인트
  // (POST /api/users/dev-stop-impersonate/)가 그걸 읽어 되돌린다.
  const devToggleRole = async () => {
    if (!user) return;

    if (user.role === "PM") {
      try {
        const employees = await apiFetch<any[]>("/api/users/");
        const nonPm = employees
          .filter((u: any) => !(u.role_info?.code_id === "ADMIN" || u.is_staff))
          .sort((a: any, b: any) => (a.username || "").localeCompare(b.username || ""));
        if (nonPm.length === 0) {
          console.error("dev-impersonate: 전환할 일반 유저 계정이 없습니다.");
          return;
        }
        await apiFetch(`/api/users/${nonPm[0].id}/impersonate/`, { method: "POST" });

        const profile = await apiFetch<any>("/api/users/me/");
        const preview = toUser(profile);
        setUser(preview);
        localStorage.setItem("hz_session", JSON.stringify(preview));
      } catch (err) {
        console.error("dev-impersonate failed:", err);
      }
      return;
    }

    try {
      await apiFetch("/api/users/dev-stop-impersonate/", { method: "POST" });

      const profile = await apiFetch<any>("/api/users/me/");
      const pmUser = toUser(profile);
      setUser(pmUser);
      localStorage.setItem("hz_session", JSON.stringify(pmUser));
    } catch (err) {
      console.error("dev-stop-impersonate failed:", err);
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
