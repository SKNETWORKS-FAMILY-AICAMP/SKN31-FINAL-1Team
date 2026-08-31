const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// access 토큰 기본 수명이 5분(SIMPLE_JWT 커스텀 설정이 없어 djangorestframework-simplejwt
// 라이브러리 기본값 그대로)이라, 이게 없으면 로그인하고 5분마다 모든 API가 401을 받고
// auth.tsx의 30초 세션 체크가 이걸 "계정 문제"로 오인해 강제 로그아웃시켰다(실사용에서
// 반드시 겪었을 문제). 여러 요청이 동시에 401을 맞아도 refresh 호출은 한 번만 나가도록
// 진행 중인 재발급 요청을 공유한다(in-flight promise).
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = typeof window === "undefined" ? null : localStorage.getItem("refresh_token");
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/api/users/token-refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: refreshToken }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    localStorage.setItem("access_token", data.access);
    return data.access as string;
  } catch {
    return null;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, isRetry = false): Promise<T> {
  const headers = new Headers(init.headers);

  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const accessToken =
    typeof window === "undefined" ? null : localStorage.getItem("access_token");
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  // login/token-refresh 자체가 401을 받는 건 "만료된 access 토큰" 문제가 아니라 진짜 인증
  // 실패이므로 재발급을 시도하지 않는다(무한 재귀 방지).
  const isAuthEndpoint = path.includes("/login/") || path.includes("/token-refresh/");
  if (response.status === 401 && !isRetry && !isAuthEndpoint) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => { refreshPromise = null; });
    }
    const newAccessToken = await refreshPromise;
    if (newAccessToken) {
      return apiFetch<T>(path, init, true);
    }
    // refresh 토큰도 만료/무효 — 진짜로 세션이 끝난 것이니 다음 요청부터는 다시 로그인해야 한다.
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("hz_session");
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.detail ?? `API 요청 실패 (${response.status})`);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
