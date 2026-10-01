// ============================================================================
// 📘 학습용 사본 — 실제 앱에서 쓰이지 않습니다. 원본: src/lib/api/client.ts
// 이 파일 하나가 "화면 ↔ 서버" 사이의 모든 통신을 대표한다. documents/page.tsx,
// auth.tsx, NewDocumentModal.tsx... 전부 결국 이 apiFetch()를 부른다.
// ============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
// 💡 process.env.NEXT_PUBLIC_... 는 "빌드할 때 정해지는 환경변수"다.
// NEXT_PUBLIC_ 접두사가 붙은 것만 브라우저(클라이언트) 쪽 코드에서 읽을 수 있다
// — 접두사 없는 환경변수(예: DB 비밀번호)는 서버에서만 쓰이고 브라우저로 안 새어나간다.

// 브라우저에 저장된 쿠키 중 특정 이름의 값을 꺼내는 작은 도우미 함수.
function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null; // 서버에서 실행될 때는 document가 없어서 방어
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// 💡 401(로그인 만료) 응답이 동시에 여러 개 오면, refresh 요청도 여러 번 나갈 수 있다
// (예: 화면에 API 호출 3개가 동시에 나갔는데 셋 다 401을 받은 경우). 그러면 서버에
// refresh 요청이 3번 가는 낭비가 생긴다. 그래서 "지금 진행 중인 refresh 요청"을
// 변수 하나에 저장해두고, 이미 진행 중이면 그 결과를 같이 기다리게(공유) 만든다.
let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/users/token-refresh/`, {
      method: "POST",
      credentials: "include",                       // 쿠키(refresh 토큰)를 같이 보냄
      headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
    });
    return res.ok; // true/false만 반환 — 성공했는지만 알면 됨
  } catch {
    return false;
  }
}

// ============================================================================
// apiFetch — 이 프로젝트의 fetch() 대체품. 제네릭 <T>는 "이 함수가 돌려주는 값의
// 타입을 호출하는 쪽에서 지정할 수 있다"는 뜻이다.
// 예: apiFetch<Task[]>("/api/tasks/assignments/") → 결과가 Task[] 타입으로 취급됨
// (실제로 서버가 그 모양을 준다는 "약속"일 뿐, TypeScript가 런타임에 검증해주는
//  건 아니다 — 그래서 서버 응답 모양이 바뀌면 이 약속이 깨질 수 있다는 걸 기억)
// ============================================================================
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},   // fetch()에 넘기는 옵션(method, body 등) 그대로 받음
  isRetry = false            // "이미 한 번 재시도한 요청인가?" — 무한 재시도 방지용
): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();

  // body가 FormData(파일 업로드)가 아니면 JSON이라고 보고 헤더를 붙인다.
  // FormData는 브라우저가 자동으로 적절한 Content-Type을 붙여주므로 손대면 안 됨.
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  // GET/HEAD/OPTIONS 이외(즉 "서버 데이터를 바꾸는" 요청)에는 CSRF 토큰을 헤더에 실음
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }

  // 진짜 요청. credentials: "include" 덕분에 로그인 쿠키가 자동으로 같이 실려간다.
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: "include" });

  // ---------------------------------------------------------------------
  // 💡 401(인증 만료) 자동 복구 로직 — 이 프로젝트에서 가장 "똑똑한" 부분
  // ---------------------------------------------------------------------
  const isAuthEndpoint = path.includes("/login/") || path.includes("/token-refresh/");
  if (response.status === 401 && !isRetry && !isAuthEndpoint) {
    // 진행 중인 refresh가 없으면 새로 시작, 있으면 그걸 같이 기다림(위에서 설명한 공유 로직)
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => { refreshPromise = null; });
    }
    const refreshed = await refreshPromise;
    if (refreshed) {
      // 재발급 성공! 원래 하려던 요청을 다시 한 번 시도한다.
      // isRetry=true를 넘기는 게 핵심 — 이번에도 401이면 더 이상 재시도 안 하고
      // 그냥 에러로 던진다(무한 루프 방지).
      return apiFetch<T>(path, init, true);
    }
    // refresh도 실패하면 아래로 내려가서 원래의 401 에러를 그대로 던진다
  }

  // ---------------------------------------------------------------------
  // 에러 처리 — 서버가 4xx/5xx를 주면 여기서 JS의 Error로 바꿔서 던진다.
  // 이렇게 해두면 호출하는 쪽에서 try { await apiFetch(...) } catch (err) { ... }
  // 로 깔끔하게 실패를 처리할 수 있다.
  // ---------------------------------------------------------------------
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null); // 에러 응답도 JSON이 아닐 수 있어 방어
    const nonFieldError = Array.isArray(errorBody?.non_field_errors) ? errorBody.non_field_errors[0] : null;
    throw new Error(errorBody?.detail ?? errorBody?.error ?? nonFieldError ?? `API 요청 실패 (${response.status})`);
  }

  if (response.status === 204) return undefined as T; // 204 = "성공했지만 돌려줄 내용 없음"
  return response.json() as Promise<T>;
}

// -----------------------------------------------------------------------------
// 🧪 스스로 확인해볼 것
// 1. 화면 코드에서 apiFetch("/api/projects/")를 부를 때, 우리가 직접 로그인 토큰을
//    헤더에 넣어준 적이 있었나? (02번 파일 다시 보기)
//    → 없다! credentials: "include" 한 줄이 브라우저에게 "쿠키 자동으로 실어 보내"를
//      시켜주기 때문에, 호출하는 쪽은 로그인 여부를 신경 안 써도 된다.
// 2. isRetry 매개변수가 없다면 어떤 문제가 생길까?
//    → refresh를 해도 여전히 401이 나오는 상황(예: 계정 자체가 잠김)에서
//      apiFetch가 자기 자신을 무한히 다시 호출하게 된다.
// -----------------------------------------------------------------------------
