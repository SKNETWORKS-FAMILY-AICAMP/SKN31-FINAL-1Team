import fs from "node:fs";
import path from "node:path";

// ── .env 로더 ────────────────────────────────────────────────────────
// dotenv 등 외부 의존성 없이 server/.env 파일을 읽어 process.env에 채워 넣는다.
// index.ts의 맨 첫 import여야 한다 — 다른 모듈(특히 aiProviderFactory.ts)이
// import 시점에 process.env를 읽으므로, 그보다 먼저 로드가 끝나 있어야 한다.
// CommonJS로 컴파일되므로 require() 순서가 곧 실행 순서라 이 보장이 성립한다.

function parseEnvFile(content: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

function loadEnvFile(): void {
  // dist/env.js 기준 서버 루트(server/.env)를 우선 찾고, 실행 위치(cwd) 기준도 백업으로 본다.
  const candidates = [path.resolve(__dirname, "../.env"), path.resolve(process.cwd(), ".env")];
  for (const p of candidates) {
    if (!fs.existsSync(p)) continue;
    let parsed: Record<string, string>;
    try {
      parsed = parseEnvFile(fs.readFileSync(p, "utf-8"));
    } catch (err) {
      console.error(`[WorkPilot AI] failed to read ${p}:`, err);
      continue;
    }
    let applied = 0;
    for (const [k, v] of Object.entries(parsed)) {
      if (process.env[k] === undefined) {
        process.env[k] = v;
        applied++;
      }
    }
    console.log(`[WorkPilot AI] loaded ${applied} value(s) from ${p}`);
    return; // 먼저 찾은 파일 하나만 사용
  }
}

loadEnvFile();
