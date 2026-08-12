// ── 픽셀 캐릭터 스프라이트 (실제 pixel-agents 스프라이트 시트 사용) ────────
// webview-ui/public/assets/characters/char_0..5.png 를 그대로 가져와 쓴다.
// 112x96, 7프레임(16px 폭) x 3방향(32px 높이). 행: 0=아래, 1=위, 2=오른쪽.
// 프레임 순서: walk1, walk2, walk3, type1, type2, read1, read2.
// (webview-ui/CLAUDE.md "Character sprites" 절 참고 — 자산 포맷이 바뀌면 여기만 고치면 된다)
const FRAME_W = 16;
const FRAME_H = 32;
const ROW_DOWN = 0;
const SCALE = 2;
const FRAME = { walk1: 0, walk2: 1, walk3: 2, type1: 3, type2: 4, read1: 5, read2: 6 };
const imageCache = [];
function getImage(palette) {
    const idx = ((palette % 6) + 6) % 6;
    let img = imageCache[idx];
    if (!img) {
        img = new Image();
        img.src = `/assets/characters/char_${idx}.png`;
        imageCache[idx] = img;
    }
    return img;
}
/** 초기 로드를 앞당겨 첫 렌더에서 빈 프레임이 보이는 시간을 줄인다. */
export function preloadCharacterSprites() {
    for (let i = 0; i < 6; i++)
        getImage(i);
}
function frameForState(state, phase) {
    switch (state) {
        case "active":
        case "delayed": {
            const f = Math.floor(phase * 5) % 2; // 빠르게 타이핑
            return f === 0 ? FRAME.type1 : FRAME.type2;
        }
        case "waiting_approval": {
            const f = Math.floor(phase * 1.6) % 2; // 천천히 읽는 느낌
            return f === 0 ? FRAME.read1 : FRAME.read2;
        }
        default: {
            const f = Math.floor(phase * 0.6) % 4;
            return f === 0 ? FRAME.walk2 : FRAME.walk1; // idle: 대기 자세, 가끔 살짝 움직임
        }
    }
}
export function drawCharacter(ctx, opts) {
    const img = getImage(opts.palette);
    const isActive = opts.state === "active";
    const bobAmount = isActive ? 1.5 : 0.6;
    const bob = Math.sin(opts.bobPhase * (isActive ? 6 : 2.2)) * bobAmount;
    const dw = FRAME_W * SCALE;
    const dh = FRAME_H * SCALE;
    const footY = opts.y;
    const dx = opts.x - dw / 2;
    const dy = footY - dh + bob;
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    // 그림자
    ctx.fillStyle = "rgba(10,10,20,0.35)";
    ctx.beginPath();
    ctx.ellipse(opts.x, footY + 1, dw * 0.3, dw * 0.1, 0, 0, Math.PI * 2);
    ctx.fill();
    const frame = frameForState(opts.state, opts.bobPhase);
    if (img.complete && img.naturalWidth > 0) {
        ctx.drawImage(img, frame * FRAME_W, ROW_DOWN * FRAME_H, FRAME_W, FRAME_H, dx, dy, dw, dh);
    }
    else {
        // 스프라이트가 아직 로드되기 전 짧은 순간의 폴백 실루엣
        ctx.fillStyle = "#4a4363";
        ctx.fillRect(dx + dw * 0.2, dy + dh * 0.15, dw * 0.6, dh * 0.85);
    }
    // Lead(PM) 표식: 별 배지
    if (opts.isLead) {
        ctx.fillStyle = "#ffd166";
        ctx.beginPath();
        drawStar(ctx, opts.x, dy - 6, 5, 7, 3.2);
        ctx.fill();
    }
    // 상태 링(발밑)
    const ringColor = opts.state === "delayed"
        ? "#ef476f"
        : opts.state === "active"
            ? "#06d6a0"
            : opts.state === "waiting_approval"
                ? "#ffd166"
                : "#5a5a72";
    ctx.strokeStyle = ringColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(opts.x, footY + 1, dw * 0.32, dw * 0.11, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
}
function drawStar(ctx, cx, cy, spikes, outerR, innerR) {
    let rot = (Math.PI / 2) * 3;
    const step = Math.PI / spikes;
    ctx.moveTo(cx, cy - outerR);
    for (let i = 0; i < spikes; i++) {
        let px = cx + Math.cos(rot) * outerR;
        let py = cy + Math.sin(rot) * outerR;
        ctx.lineTo(px, py);
        rot += step;
        px = cx + Math.cos(rot) * innerR;
        py = cy + Math.sin(rot) * innerR;
        ctx.lineTo(px, py);
        rot += step;
    }
    ctx.lineTo(cx, cy - outerR);
    ctx.closePath();
}
// ── 책상/모니터 ──────────────────────────────────────────────────────
// 진짜 등각(isometric) 자산은 없어서, 살짝 원근감을 준 사다리꼴 상판 + 모니터로
// "실제 사무실 데스크" 느낌을 낸다. 모니터 화면은 작업 상태에 따라 빛난다.
const DECOR_SEED_ITEMS = ["plant", "mug", "books"];
function decorFor(seed) {
    return DECOR_SEED_ITEMS[seed % DECOR_SEED_ITEMS.length];
}
const DESK_W = 68;
const DESK_DEPTH = 16; // 상판 원근 깊이
const DESK_LEG_H = 20;
export function drawDesk(ctx, opts) {
    const { x, y } = opts;
    const topY = y - DESK_LEG_H;
    const halfW = DESK_W / 2;
    const skew = 6; // 상판 원근용 좌우 기울임
    ctx.save();
    // 책상 아래 카펫(은은한 타원)
    ctx.fillStyle = "rgba(0,0,0,0.18)";
    ctx.beginPath();
    ctx.ellipse(x, y + 3, halfW + 6, 7, 0, 0, Math.PI * 2);
    ctx.fill();
    // 다리/전면 패널
    ctx.fillStyle = "#3a3454";
    ctx.fillRect(x - halfW + 4, topY + DESK_DEPTH, DESK_W - 8, DESK_LEG_H - 4);
    ctx.fillStyle = "#332e4a";
    ctx.fillRect(x - halfW + 4, topY + DESK_DEPTH + DESK_LEG_H - 8, DESK_W - 8, 4);
    // 상판 (사다리꼴로 살짝 원근)
    ctx.fillStyle = "#5c5480";
    ctx.beginPath();
    ctx.moveTo(x - halfW, topY + DESK_DEPTH);
    ctx.lineTo(x - halfW + skew, topY);
    ctx.lineTo(x + halfW - skew, topY);
    ctx.lineTo(x + halfW, topY + DESK_DEPTH);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#6b6296";
    ctx.beginPath();
    ctx.moveTo(x - halfW, topY + DESK_DEPTH);
    ctx.lineTo(x - halfW + skew, topY);
    ctx.lineTo(x - halfW + skew + 6, topY);
    ctx.lineTo(x - halfW + 6, topY + DESK_DEPTH);
    ctx.closePath();
    ctx.fill(); // 상판 하이라이트 스트라이프
    // 모니터
    const monW = 22;
    const monH = 15;
    const monX = x - monW / 2;
    const monY = topY - monH + 2;
    ctx.fillStyle = "#232030";
    ctx.fillRect(monX - 2, monY - 2, monW + 4, monH + 6);
    const glow = opts.state === "active"
        ? `rgba(6,214,160,${0.55 + Math.sin(opts.glowPhase * 6) * 0.25})`
        : opts.state === "delayed"
            ? `rgba(239,71,111,${0.5 + Math.sin(opts.glowPhase * 4) * 0.2})`
            : opts.state === "waiting_approval"
                ? `rgba(255,209,102,0.55)`
                : "#14121e";
    ctx.fillStyle = glow;
    ctx.fillRect(monX, monY, monW, monH);
    if (opts.state === "active") {
        // 코드 라인처럼 보이는 가는 줄무늬
        ctx.fillStyle = "rgba(10,20,15,0.5)";
        for (let i = 0; i < 4; i++) {
            const lw = 6 + ((Math.floor(opts.glowPhase * 3) + i) % 4) * 3;
            ctx.fillRect(monX + 2, monY + 2 + i * 3, lw, 1.5);
        }
    }
    ctx.fillStyle = "#3a3454";
    ctx.fillRect(x - 3, monY + monH, 6, 4); // 모니터 스탠드
    // 키보드
    ctx.fillStyle = "#2c2840";
    ctx.fillRect(x - 10, topY + DESK_DEPTH - 5, 20, 5);
    // 랜덤 소품
    const item = decorFor(opts.seed);
    const itemX = x + halfW - 12;
    const itemY = topY + DESK_DEPTH - 4;
    if (item === "plant") {
        ctx.fillStyle = "#4a7a5a";
        ctx.beginPath();
        ctx.ellipse(itemX, itemY - 6, 5, 7, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#7a5a45";
        ctx.fillRect(itemX - 3, itemY - 2, 6, 4);
    }
    else if (item === "mug") {
        ctx.fillStyle = "#ef8a5f";
        ctx.fillRect(itemX - 3, itemY - 6, 6, 6);
    }
    else {
        ctx.fillStyle = "#e0a458";
        ctx.fillRect(itemX - 4, itemY - 6, 8, 3);
        ctx.fillStyle = "#8ecae6";
        ctx.fillRect(itemX - 4, itemY - 3, 8, 3);
    }
    ctx.restore();
}
// ── 배경 장식(식물/책장) ─────────────────────────────────────────────
export function drawPlant(ctx, x, y, scale = 1) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(scale, scale);
    ctx.fillStyle = "rgba(0,0,0,0.2)";
    ctx.beginPath();
    ctx.ellipse(0, 2, 14, 4, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#6b4a35";
    ctx.beginPath();
    ctx.moveTo(-10, 0);
    ctx.lineTo(10, 0);
    ctx.lineTo(7, -14);
    ctx.lineTo(-7, -14);
    ctx.closePath();
    ctx.fill();
    const leafColors = ["#3f7a52", "#4f8f61", "#387048"];
    for (let i = 0; i < 6; i++) {
        ctx.fillStyle = leafColors[i % leafColors.length];
        const angle = (i / 6) * Math.PI * 2;
        const lx = Math.cos(angle) * 12;
        const ly = -20 + Math.sin(angle) * 10;
        ctx.beginPath();
        ctx.ellipse(lx, ly, 9, 5, angle, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.restore();
}
export function drawBookshelf(ctx, x, y, w = 64) {
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,0.2)";
    ctx.fillRect(x - w / 2, y + 2, w, 5);
    ctx.fillStyle = "#4a3a2c";
    ctx.fillRect(x - w / 2, y - 46, w, 48);
    ctx.fillStyle = "#3a2d22";
    for (let row = 0; row < 2; row++) {
        ctx.fillRect(x - w / 2 + 3, y - 42 + row * 22, w - 6, 16);
    }
    const bookColors = ["#c1666b", "#4f8f61", "#e0a458", "#8ecae6", "#9b5de5"];
    for (let row = 0; row < 2; row++) {
        let bx = x - w / 2 + 5;
        let i = 0;
        while (bx < x + w / 2 - 6) {
            const bw = 3 + (i % 3);
            ctx.fillStyle = bookColors[(row * 3 + i) % bookColors.length];
            ctx.fillRect(bx, y - 40 + row * 22, bw, 12);
            bx += bw + 1;
            i++;
        }
    }
    ctx.restore();
}
export function drawSpeechBubble(ctx, x, y, kind) {
    const w = 34;
    const h = 22;
    const bx = x - w / 2;
    const by = y - h - 10;
    const bg = kind === "delay" ? "#ef476f" : kind === "done" ? "#06d6a0" : "#2a2a3a";
    const glyph = kind === "delay" ? "!" : kind === "done" ? "✓" : "···";
    ctx.save();
    ctx.fillStyle = bg;
    roundRect(ctx, bx, by, w, h, 5);
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(x - 5, by + h);
    ctx.lineTo(x + 5, by + h);
    ctx.lineTo(x, by + h + 7);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 13px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(glyph, x, by + h / 2 + 1);
    ctx.restore();
}
// ── 활동 라벨 ────────────────────────────────────────────────────────
// 캐릭터 머리 위에 지금 하고 있는 작업명을 짧게 보여준다(참고 스크린샷의
// "Designing"/"Coding" 라벨과 같은 역할).
export function drawActivityLabel(ctx, x, y, text, state) {
    const trimmed = text.length > 16 ? `${text.slice(0, 15)}…` : text;
    ctx.save();
    ctx.font = "10px monospace";
    const padX = 6;
    const w = ctx.measureText(trimmed).width + padX * 2;
    const h = 15;
    const color = state === "delayed" ? "#ef476f" : state === "active" ? "#06d6a0" : state === "waiting_approval" ? "#ffd166" : "#8a8aa0";
    ctx.fillStyle = "rgba(15,15,24,0.82)";
    roundRect(ctx, x - w / 2, y - h, w, h, 4);
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    roundRect(ctx, x - w / 2, y - h, w, h, 4);
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(trimmed, x, y - h / 2 + 1);
    ctx.restore();
}
function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
}
