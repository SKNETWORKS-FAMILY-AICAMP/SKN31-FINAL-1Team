import type { IncomingMessage, ServerResponse } from "node:http";

// ── 아주 작은 HTTP 라우터/유틸 (외부 프레임워크 의존성 없음) ─────────────

export interface Ctx {
  req: IncomingMessage;
  res: ServerResponse;
  params: Record<string, string>;
  query: URLSearchParams;
  body: unknown;
}

export type Handler = (ctx: Ctx) => void | Promise<void>;

interface Route {
  method: string;
  segments: string[]; // "/api/tasks/:id/approve" -> ["api","tasks",":id","approve"]
  handler: Handler;
}

export class Router {
  private routes: Route[] = [];

  add(method: string, path: string, handler: Handler) {
    this.routes.push({
      method: method.toUpperCase(),
      segments: path.split("/").filter(Boolean),
      handler,
    });
  }
  get(path: string, h: Handler) { this.add("GET", path, h); }
  post(path: string, h: Handler) { this.add("POST", path, h); }

  match(method: string, pathname: string): { handler: Handler; params: Record<string, string> } | null {
    const segs = pathname.split("/").filter(Boolean);
    for (const r of this.routes) {
      if (r.method !== method.toUpperCase()) continue;
      if (r.segments.length !== segs.length) continue;
      const params: Record<string, string> = {};
      let ok = true;
      for (let i = 0; i < r.segments.length; i++) {
        const rs = r.segments[i]!;
        const s = segs[i]!;
        if (rs.startsWith(":")) params[rs.slice(1)] = decodeURIComponent(s);
        else if (rs !== s) { ok = false; break; }
      }
      if (ok) return { handler: r.handler, params };
    }
    return null;
  }
}

export function sendJson(res: ServerResponse, status: number, data: unknown) {
  const body = JSON.stringify(data, null, 2);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

// 회의 요약에 문서/음성 첨부파일을 base64로 실어 보낼 수 있어서, 기본 바디 파서에도 상한을
// 둔다(첨부 없는 요청은 몇 KB 수준이라 평소엔 아무 영향이 없다). 음성 파일은 특히 wav 등
// 비압축 포맷이면 몇 분짜리도 수십 MB가 흔해서, base64 팽창(~33%)까지 감안해 넉넉히 잡는다.
const MAX_BODY_BYTES = 80 * 1024 * 1024; // 80MB

export function readJsonBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    let rejected = false;
    req.on("data", (c: Buffer) => {
      if (rejected) return; // 상한 초과 후 들어오는 데이터는 버퍼링하지 않고 흘려보내기만 한다
      size += c.length;
      if (size > MAX_BODY_BYTES) {
        rejected = true;
        chunks.length = 0; // 이미 받은 것도 더 들고 있을 필요 없음
        reject(new HttpError(413, "request body too large (첨부파일 용량 합계는 80MB 이하로 줄여주세요)"));
        // 주의: 여기서 req.destroy()를 호출하면 안 된다 — 요청/응답이 같은 TCP 소켓을 쓰기
        // 때문에 소켓을 바로 끊으면 413 JSON을 보내기도 전에 연결이 리셋돼, 클라이언트는
        // 정상 에러 응답 대신 "Failed to fetch"(연결 재설정)만 보게 된다. 소켓은 그대로 두고
        // 남은 바이트는 계속 흘려보내(버리기만 하고) 정상적으로 413 응답을 내려보낸다.
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => {
      if (rejected) return;
      if (chunks.length === 0) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf-8")));
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", (err) => {
      if (!rejected) reject(err);
    });
  });
}

export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
