// pdf-parse/mammoth는 자체 타입 선언을 배포하지 않아, 여기서 실제로 쓰는 부분만 최소한으로
// 선언한다(@types 패키지를 추가로 설치할 필요 없이 tsc가 통과하게 하는 목적).

declare module "pdf-parse" {
  interface PDFParseResult {
    text: string;
    numpages?: number;
    numrender?: number;
    info?: unknown;
    metadata?: unknown;
    version?: string;
  }
  function pdfParse(dataBuffer: Buffer, options?: Record<string, unknown>): Promise<PDFParseResult>;
  export = pdfParse;
}

declare module "mammoth" {
  interface ExtractRawTextResult {
    value: string;
    messages: unknown[];
  }
  export function extractRawText(input: { buffer: Buffer } | { path: string }): Promise<ExtractRawTextResult>;
}
