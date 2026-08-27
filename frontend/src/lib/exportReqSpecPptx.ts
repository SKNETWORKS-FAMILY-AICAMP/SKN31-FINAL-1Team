import type { ReqSpecDoc } from "@/lib/documentTemplates";

// 슬라이드 한 장에 표를 다 넣으면 행이 넘쳐 글자가 깨지므로, 한 슬라이드에 담을 최대 행 수를 정해두고
// 이보다 많으면 여러 슬라이드로 나눠 찍는다(아래 chunkCount 계산에서 사용).
const ROWS_PER_SLIDE = 8;

// ReqSpecDoc(요구사항정의서 단일 스키마)을 표 형태 슬라이드로 페이지네이션해서 내보낸다.
export async function exportReqSpecPptx(doc: ReqSpecDoc, title: string) {
  const PptxGenJS = (await import("pptxgenjs")).default;
  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: "A4", width: 10, height: 5.63 });
  pptx.layout = "A4";

  const TITLE_COLOR = "1E293B";
  const ACCENT = "2563EB";
  const HEADER_FILL = "F1F5F9";

  const titleSlide = pptx.addSlide();
  titleSlide.addText(title, { x: 0.5, y: 2.1, w: 9, h: 1, fontSize: 32, bold: true, color: TITLE_COLOR });
  titleSlide.addText("요구사항정의서", { x: 0.5, y: 3.0, w: 9, h: 0.5, fontSize: 18, color: ACCENT });

  const headerRow = [
    { text: "ID", options: { bold: true, fill: { color: HEADER_FILL } } },
    { text: "대분류", options: { bold: true, fill: { color: HEADER_FILL } } },
    { text: "중분류", options: { bold: true, fill: { color: HEADER_FILL } } },
    { text: "요구사항명", options: { bold: true, fill: { color: HEADER_FILL } } },
    { text: "기능설명", options: { bold: true, fill: { color: HEADER_FILL } } },
    { text: "비고", options: { bold: true, fill: { color: HEADER_FILL } } },
  ];

  const items = doc.items.length ? doc.items : [];
  // 항목이 하나도 없어도 "항목 없음" 슬라이드는 한 장 보여줘야 하므로 최소 1로 보정.
  const chunkCount = Math.max(1, Math.ceil(items.length / ROWS_PER_SLIDE));

  // ROWS_PER_SLIDE개씩 잘라(slice) 슬라이드를 순서대로 채운다 - 라이브러리의 자동 페이지 분할(autoPage) 대신
  // 우리가 직접 청크 단위로 나눠서 각 슬라이드에 몇 번째 페이지인지(1/3 등) 표시할 수 있게 한다.
  for (let c = 0; c < chunkCount; c++) {
    const chunk = items.slice(c * ROWS_PER_SLIDE, (c + 1) * ROWS_PER_SLIDE);
    const slide = pptx.addSlide();
    slide.addText(
      `요구사항 목록${chunkCount > 1 ? ` (${c + 1}/${chunkCount})` : ""}`,
      { x: 0.5, y: 0.3, w: 9, h: 0.5, fontSize: 20, bold: true, color: ACCENT }
    );
    const rows: any[] = [
      headerRow,
      ...(chunk.length ? chunk.map(item => [
        { text: item.id, options: { fontSize: 8, fontFace: "Consolas" } },
        { text: item.category, options: { fontSize: 9 } },
        { text: item.subCategory, options: { fontSize: 9 } },
        { text: item.name, options: { fontSize: 9, bold: true } },
        { text: item.description, options: { fontSize: 8 } },
        { text: item.note, options: { fontSize: 8, color: "64748B" } },
      ]) : [[{ text: "항목이 없습니다.", options: { colspan: 6, align: "center", color: "94A3B8" } }]]),
    ];
    slide.addTable(rows, {
      x: 0.4, y: 1.0, w: 9.2,
      // ID/대분류/중분류/요구사항명/기능설명/비고 순서대로, 내용이 긴 컬럼(기능설명)에 더 넓은 폭을 배분.
      colW: [1.0, 0.9, 0.9, 1.7, 3.4, 1.3],
      fontSize: 9, color: TITLE_COLOR,
      border: { type: "solid", color: "E2E8F0", pt: 1 },
      // 페이지 분할은 위에서 이미 chunk 단위로 직접 처리했으므로 라이브러리의 자동 분할은 꺼둔다.
      autoPage: false,
      valign: "top",
    });
  }

  await pptx.writeFile({ fileName: `${title}_요구사항정의서.pptx` });
}
