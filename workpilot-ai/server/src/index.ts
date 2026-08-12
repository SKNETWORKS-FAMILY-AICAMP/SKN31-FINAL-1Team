import "./env.js"; // server/.env 로드 — 다른 모든 import보다 먼저 실행되어야 한다
import { createServer } from "./httpServer.js";
import { startAutopilot } from "./autopilot.js";

const port = Number(process.env.PORT ?? 4100);
createServer(port);
startAutopilot();
