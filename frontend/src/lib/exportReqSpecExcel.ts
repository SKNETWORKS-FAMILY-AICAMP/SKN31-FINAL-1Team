import type { ReqSpecDoc } from "@/lib/documentTemplates";

// ReqSpecDoc(요구사항정의서 단일 스키마)을 원본 요구사항정의서 양식과 동일한 컬럼 구성의 엑셀로 내보낸다.
export async function exportReqSpecExcel(doc: ReqSpecDoc, title: string) {
  // xlsx는 export 시점에만 필요하므로 동적 import로 초기 번들에서 제외한다.
  const XLSX = await import("xlsx");

  // 객체 키 이름이 그대로 엑셀 헤더가 되므로, 한글 키를 써서 헤더 행을 자동으로 만든다.
  const rows = doc.items.map(item => ({
    "요구사항 ID": item.id,
    "대분류": item.category,
    "중분류": item.subCategory,
    "요구사항명": item.name,
    "기능설명": item.description,
    "비고": item.note,
  }));

  const sheet = XLSX.utils.json_to_sheet(rows);
  // 위 rows 컬럼 순서(ID/대분류/중분류/요구사항명/기능설명/비고)와 동일한 순서로 각 컬럼 너비(문자 수 기준)를 지정.
  sheet["!cols"] = [
    { wch: 14 }, { wch: 12 }, { wch: 12 }, { wch: 24 }, { wch: 48 }, { wch: 20 },
  ];

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, "요구사항정의서");
  XLSX.writeFile(workbook, `${title}_요구사항정의서.xlsx`);
}
