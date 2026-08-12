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

export function readJsonBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      if (chunks.length === 0) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf-8")));
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
