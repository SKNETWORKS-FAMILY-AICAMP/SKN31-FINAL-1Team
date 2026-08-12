import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { buildRouter } from "./routes.js";
import { HttpError, readJsonBody, sendJson } from "./http.js";
import type { Ctx } from "./http.js";

// server/dist/httpServer.js 기준(CommonJS라 __dirname을 그대로 쓸 수 있다) -> ../../web/public
const PUBLIC_DIR = path.resolve(__dirname, "../../web/public");
// pipeline.ts의 OUTPUT_ROOT와 동일한 경로(server/output) — AI가 생성한 결과물 파일을 /files/ 로 내려준다.
const OUTPUT_DIR = path.resolve(__dirname, "../output");

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

function serveStatic(reqPath: string, res: http.ServerResponse): boolean {
  let rel = reqPath === "/" ? "/index.html" : reqPath;
  const filePath = path.join(PUBLIC_DIR, rel);
  if (!filePath.startsWith(PUBLIC_DIR)) return false; // path traversal 방지
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) return false;
  const ext = path.extname(filePath);
  const buf = fs.readFileSync(filePath);
  res.writeHead(200, { "Content-Type": MIME[ext] ?? "application/octet-stream" });
  res.end(buf);
  return true;
}

// AI가 생성한 결과물(코드/문서) 파일을 브라우저에서 바로 보거나 받을 수 있게 서빙한다.
// /files/<projectId>/<filename> -> server/output/<projectId>/<filename>
function serveOutputFile(reqPath: string, res: http.ServerResponse): boolean {
  const rel = reqPath.replace(/^\/files\//, "");
  const filePath = path.join(OUTPUT_DIR, rel);
  if (!filePath.startsWith(OUTPUT_DIR)) return false; // path traversal 방지
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) return false;
  const buf = fs.readFileSync(filePath);
  res.writeHead(200, {
    "Content-Type": "text/plain; charset=utf-8",
    "Content-Disposition": `inline; filename="${path.basename(filePath)}"`,
  });
  res.end(buf);
  return true;
}

export function createServer(port: number) {
  const router = buildRouter();

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url ?? "/", `http://localhost:${port}`);

      if (req.method === "OPTIONS") {
        res.writeHead(204, {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        });
        res.end();
        return;
      }

      if (req.method === "GET" && url.pathname.startsWith("/files/")) {
        if (serveOutputFile(url.pathname, res)) return;
        sendJson(res, 404, { error: "file not found" });
        return;
      }

      if (url.pathname.startsWith("/api/")) {
        const matched = router.match(req.method ?? "GET", url.pathname);
        if (!matched) {
          sendJson(res, 404, { error: `no route for ${req.method} ${url.pathname}` });
          return;
        }
        const ctx: Ctx = {
          req,
          res,
          params: matched.params,
          query: url.searchParams,
          body: undefined,
        };
        if (req.method === "POST") {
          try {
            ctx.body = await readJsonBody(req);
          } catch (err) {
            if (err instanceof HttpError) throw err; // 예: 413 첨부파일 용량 초과 — 그대로 전달
            ctx.body = {}; // 그 외(JSON 파싱 실패 등)는 기존처럼 빈 바디로 흡수
          }
        }
        await matched.handler(ctx);
        return;
      }

      if (req.method === "GET" && serveStatic(url.pathname, res)) return;
      if (req.method === "GET") {
        // SPA fallback
        if (serveStatic("/index.html", res)) return;
      }

      sendJson(res, 404, { error: "not found" });
    } catch (err) {
      if (err instanceof HttpError) {
        sendJson(res, err.status, { error: err.message });
      } else {
        console.error("[WorkPilot AI] unhandled error:", err);
        sendJson(res, 500, { error: "internal server error" });
      }
    }
  });

  server.listen(port, () => {
    console.log(`[WorkPilot AI] server listening on http://localhost:${port}`);
    console.log(`[WorkPilot AI] serving static frontend from ${PUBLIC_DIR}`);
  });

  return server;
}
