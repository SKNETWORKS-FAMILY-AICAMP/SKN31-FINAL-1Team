const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
 
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
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
 
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.detail ?? `API 요청 실패 (${response.status})`);
  }
 
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}