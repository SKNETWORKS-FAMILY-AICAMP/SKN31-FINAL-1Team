// ── 회의 요약 첨부파일 처리 ──────────────────────────────────────────
// 회의 요약은 타이핑한 텍스트뿐 아니라 문서(txt/md/pdf/docx)나 음성 파일도 첨부할 수 있다.
// 클라이언트가 파일을 base64로 인코딩해 JSON으로 올리면(별도 업로드 프레임워크 없이 기존
// JSON 바디 파이프라인을 그대로 재사용하기 위함), 여기서 실제 내용을 추출해 회의 원문
// 텍스트에 이어붙인다 — 이후 파이프라인(summarizeMeeting 등)은 첨부 여부를 신경 쓸 필요가
// 없다.
//
// pdf/docx 추출에는 pdf-parse/mammoth를 쓴다 — 이 서버가 지켜온 "외부 런타임 의존성 없음"
// 원칙의 유일한 예외다(README 참고). 음성 파일은 OpenAI Whisper API로 전사한다 — Claude는
// 오디오 입력을 지원하지 않으므로, 선택된 텍스트 프로바이더와 무관하게 OPENAI_API_KEY가
// 있을 때만 동작한다.

export interface MeetingAttachment {
  name: string;
  mimeType?: string;
  /** data URL 전체("data:audio/mpeg;base64,...")나 순수 base64 문자열 둘 다 허용한다. */
  dataBase64: string;
}

interface ExtractedAttachment {
  name: string;
  ok: boolean;
  /** ok=true면 추출된 텍스트, ok=false면 사용자에게 보여줄 실패 사유. */
  text: string;
}

const TEXT_EXTENSIONS = /\.(txt|md|markdown|log|csv)$/i;
const PDF_EXTENSIONS = /\.pdf$/i;
const DOCX_EXTENSIONS = /\.docx$/i;
const AUDIO_EXTENSIONS = /\.(mp3|m4a|mp4|wav|webm|ogg|mpeg|mpga|flac)$/i;

function stripDataUrlPrefix(dataBase64: string): string {
  const m = dataBase64.match(/^data:[^;]+;base64,(.+)$/s);
  return m ? m[1]! : dataBase64;
}

function isTextLike(name: string, mimeType?: string): boolean {
  if (mimeType?.startsWith("text/")) return true;
  return TEXT_EXTENSIONS.test(name);
}

function isPdf(name: string, mimeType?: string): boolean {
  return mimeType === "application/pdf" || PDF_EXTENSIONS.test(name);
}

function isDocx(name: string, mimeType?: string): boolean {
  return (
    mimeType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    DOCX_EXTENSIONS.test(name)
  );
}

function isAudio(name: string, mimeType?: string): boolean {
  if (mimeType?.startsWith("audio/")) return true;
  return AUDIO_EXTENSIONS.test(name);
}

async function loadPdfParse() {
  try {
    const mod = await import("pdf-parse");
    return mod.default;
  } catch {
    throw new Error("pdf-parse가 설치되어 있지 않습니다 — workpilot-ai/server에서 npm install을 먼저 실행하세요.");
  }
}

async function loadMammothExtractRawText() {
  try {
    const mod = await import("mammoth");
    return mod.extractRawText;
  } catch {
    throw new Error("mammoth가 설치되어 있지 않습니다 — workpilot-ai/server에서 npm install을 먼저 실행하세요.");
  }
}

// 첨부파일 하나당 상한 — 특히 OpenAI Whisper API 자체가 파일당 25MB를 고정으로 강제해서
// (우리 쪽 80MB 전체 바디 제한과는 별개, 서버가 늘릴 수 없는 값) 다른 형식도 동일하게
// 맞춰서 일관된 규칙 하나로 안내한다. 클라이언트(main.ts)에서도 같은 값으로 먼저 걸러서
// 애초에 업로드/전사 API 호출까지 가지 않게 한다.
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024; // 25MB

function extractApiErrorMessage(body: string): string {
  try {
    const parsed = JSON.parse(body) as { error?: { message?: string } };
    if (parsed.error?.message) return parsed.error.message;
  } catch {
    /* JSON이 아니면 원문 일부를 그대로 쓴다 */
  }
  return body.slice(0, 200);
}

async function transcribeAudio(buffer: Buffer, name: string, mimeType: string): Promise<string> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error(
      "음성 전사에는 OPENAI_API_KEY가 필요합니다 (server/.env에 설정하세요 — 텍스트 요약에 Claude를 쓰는 중이어도 전사는 Whisper API라 별도로 필요합니다)."
    );
  }
  // 크기 자체는 extractAttachmentText의 공통 상한 체크에서 이미 걸러지지만, 혹시 모를 경로
  // 누락에 대비해 여기서도 한 번 더 확인한다(방어적 이중 체크).
  if (buffer.length > MAX_ATTACHMENT_BYTES) {
    const mb = (buffer.length / (1024 * 1024)).toFixed(1);
    throw new Error(
      `음성 파일이 너무 큽니다 (${mb}MB) — OpenAI Whisper API는 파일 하나당 25MB까지만 허용합니다(서버가 늘릴 수 없는 제한입니다). ` +
        `녹음 편집기로 더 짧게 잘라서 나눠 올리거나, 낮은 비트레이트로 압축한 뒤 다시 시도해주세요.`
    );
  }
  const form = new FormData();
  // Buffer는 SharedArrayBuffer 백업 가능성 때문에 BlobPart 타입과 안 맞을 수 있어
  // 표준 ArrayBuffer 기반 Uint8Array로 복사해서 넘긴다.
  form.append("file", new Blob([Uint8Array.from(buffer)], { type: mimeType || "audio/mpeg" }), name);
  form.append("model", process.env.WORKPILOT_WHISPER_MODEL || "whisper-1");
  let res: Response;
  try {
    res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: { authorization: `Bearer ${apiKey}` },
      body: form,
    });
  } catch (err) {
    throw new Error(`Whisper API 호출 실패: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    if (res.status === 413) {
      throw new Error("음성 파일이 너무 커서 Whisper API가 거부했습니다(파일당 25MB 제한). 더 짧게 잘라서 다시 시도해주세요.");
    }
    throw new Error(`Whisper API 오류 (HTTP ${res.status}): ${extractApiErrorMessage(body)}`);
  }
  const data = (await res.json()) as { text?: string };
  if (!data.text || !data.text.trim()) throw new Error("Whisper 응답에 전사된 텍스트가 없습니다.");
  return data.text.trim();
}

async function extractAttachmentText(att: MeetingAttachment): Promise<ExtractedAttachment> {
  const { name, mimeType } = att;
  try {
    const base64 = stripDataUrlPrefix(att.dataBase64);
    const buffer = Buffer.from(base64, "base64");
    if (buffer.length === 0) throw new Error("빈 파일입니다.");
    if (buffer.length > MAX_ATTACHMENT_BYTES) {
      const mb = (buffer.length / (1024 * 1024)).toFixed(1);
      throw new Error(`파일이 너무 큽니다 (${mb}MB) — 첨부파일은 25MB 이하만 지원합니다.`);
    }

    if (isTextLike(name, mimeType)) {
      const text = buffer.toString("utf8").trim();
      if (!text) throw new Error("파일 내용이 비어 있습니다.");
      return { name, ok: true, text };
    }
    if (isPdf(name, mimeType)) {
      // 지연 로딩: pdf-parse/mammoth는 이 서버의 유일한 런타임 의존성이라, pdf/docx를 실제로
      // 올리기 전까지는 모듈을 건드리지 않는다 — npm install 전에도 텍스트/음성 첨부는
      // 정상 동작하고, pdf/docx만 "처리 실패" 메시지로 우아하게 저하되게 하기 위함이다.
      const pdfParse = await loadPdfParse();
      const result = await pdfParse(buffer);
      const text = result.text.trim();
      if (!text) throw new Error("PDF에서 텍스트를 추출하지 못했습니다(스캔 이미지일 수 있습니다).");
      return { name, ok: true, text };
    }
    if (isDocx(name, mimeType)) {
      const extractRawText = await loadMammothExtractRawText();
      const result = await extractRawText({ buffer });
      const text = result.value.trim();
      if (!text) throw new Error("문서에서 텍스트를 추출하지 못했습니다.");
      return { name, ok: true, text };
    }
    if (isAudio(name, mimeType)) {
      const text = await transcribeAudio(buffer, name, mimeType || "audio/mpeg");
      return { name, ok: true, text };
    }
    throw new Error(
      `지원하지 않는 파일 형식입니다 (${mimeType || "확장자 미상"}). txt/md/pdf/docx 문서나 음성 파일만 지원합니다.`
    );
  } catch (err) {
    return { name, ok: false, text: err instanceof Error ? err.message : String(err) };
  }
}

/** 첨부파일 여러 개를 병렬로 처리해서 회의 원문 텍스트 뒤에 이어붙일 블록 하나로 합친다.
 * 실패한 파일도(전사 실패 등) 사유를 블록에 남겨서 전체 요약이 조용히 누락되지 않게 한다. */
export async function buildAttachmentsBlock(attachments: MeetingAttachment[]): Promise<string> {
  if (attachments.length === 0) return "";
  const results = await Promise.all(attachments.map(extractAttachmentText));
  return results
    .map((r) =>
      r.ok ? `\n\n--- 첨부: ${r.name} ---\n${r.text}` : `\n\n--- 첨부: ${r.name} (처리 실패) ---\n[${r.text}]`
    )
    .join("");
}
