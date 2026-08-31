const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// 2026-08-31: access/refresh 토큰을 localStorage 대신 HttpOnly 쿠키로 옮겼다(XSS로 JS가
// 토큰을 읽어갈 수 있는 경로를 막기 위함) — 그래서 이제 이 파일에서 토큰을 직접 읽거나
// Authorization 헤더에 실을 필요가 없다. credentials: "include"만 있으면 브라우저가
// 쿠키를 알아서 요청에 실어 보낸다. 대신 쿠키는 자동으로 실리는 만큼 CSRF에 노출되므로,
// GET이 아닌 요청에는 Django의 csrftoken 쿠키 값을 X-CSRFToken 헤더로 같이 보내야 한다.
function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// access 토큰 기본 수명이 5분(SIMPLE_JWT 커스텀 설정이 없어 djangorestframework-simplejwt
// 라이브러리 기본값 그대로)이라, 이게 없으면 로그인하고 5분마다 모든 API가 401을 받고
// auth.tsx의 30초 세션 체크가 이걸 "계정 문제"로 오인해 강제 로그아웃시켰다(실사용에서
// 반드시 겪었을 문제). 여러 요청이 동시에 401을 맞아도 refresh 호출은 한 번만 나가도록
// 진행 중인 재발급 요청을 공유한다(in-flight promise).
let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/users/token-refresh/`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, isRetry = false): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();

  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  // 쓰기 요청(POST/PATCH/PUT/DELETE)에만 CSRF 토큰을 실어 보낸다 — GET은 CSRF 대상이 아니다.
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: "include" });

  // login/token-refresh 자체가 401을 받는 건 "만료된 access 토큰" 문제가 아니라 진짜 인증
  // 실패이므로 재발급을 시도하지 않는다(무한 재귀 방지).
  const isAuthEndpoint = path.includes("/login/") || path.includes("/token-refresh/");
  if (response.status === 401 && !isRetry && !isAuthEndpoint) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => { refreshPromise = null; });
    }
    const refreshed = await refreshPromise;
    if (refreshed) {
      return apiFetch<T>(path, init, true);
    }
    // refresh 토큰도 만료/무효 — 진짜로 세션이 끝난 것. 쿠키 정리는 서버(로그아웃 API)가
    // 담당하므로 여기선 그냥 원래 401 에러를 그대로 던진다(호출부가 로그인 화면으로 유도).
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.detail ?? errorBody?.error ?? `API 요청 실패 (${response.status})`);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
