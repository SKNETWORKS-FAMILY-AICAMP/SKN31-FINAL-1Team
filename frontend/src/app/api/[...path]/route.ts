import { NextRequest } from "next/server";

// 2026-09-17: 프론트(vercel.app)와 백엔드(duckdns.org)가 서로 다른 도메인이라, 백엔드가
// 내려주는 쿠키(csrftoken/access_token 등)가 브라우저에는 "제3자 쿠키"로 보여 차단당했다
// (Safari/Firefox는 기본 차단, Chrome도 점점 같은 방향). next.config.ts의 rewrites()로
// 우회를 시도했으나, 그 방식은 목적지 주소가 빌드 시점에 고정되고(런타임 env 변경이 반영
// 안 됨) 외부 도메인 + 캐치올 패턴 조합에서 자기 자신으로 리다이렉트되는 문제가 있었다
// (Turbopack의 외부 rewrite 처리 이슈로 추정). 대신 여기서 직접 요청을 백엔드로 중계한다 —
// 브라우저는 항상 프론트와 같은 도메인에만 요청하므로 쿠키가 "같은 도메인"에서 온 것으로
// 보여 정상 저장/전송된다.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

// 2026-09-28 (서비스 테스트 보고서 IS-001): 이 함수가 미국 리전(iad1)에서 실행되면서
// 서울에 있는 백엔드(EC2)까지의 왕복 시간이 추가로 붙어, 직접 호출 대비 요청마다 약
// 0.75초가 더 걸렸다(프록시 평균 0.79초 vs 직접 0.04초, 실측). 리전 고정은 route 세그먼트
// 설정(preferredRegion, Next.js에서 지원 중단됨) 대신 프로젝트 루트의 vercel.json
// "regions" 설정으로 서울(icn1)에 고정한다.

async function proxy(req: NextRequest) {
  const backendUrl = `${BACKEND_ORIGIN}${req.nextUrl.pathname}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("content-length");

  const hasBody = !["GET", "HEAD"].includes(req.method);

  const backendRes = await fetch(backendUrl, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
  });

  // 백엔드가 한 응답에서 access_token/refresh_token처럼 쿠키를 두 개 이상 내려줄 수 있는데,
  // Headers를 그냥 복사하면 여러 Set-Cookie가 쉼표로 합쳐져 깨진다 — getSetCookie()로 각각 꺼내
  // 따로 붙여야 한다.
  const headersOut = new Headers();
  backendRes.headers.forEach((value, key) => {
    if (key.toLowerCase() === "set-cookie") return;
    headersOut.append(key, value);
  });
  for (const cookie of backendRes.headers.getSetCookie()) {
    headersOut.append("set-cookie", cookie);
  }

  return new Response(backendRes.body, { status: backendRes.status, headers: headersOut });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as OPTIONS,
  proxy as HEAD,
};
