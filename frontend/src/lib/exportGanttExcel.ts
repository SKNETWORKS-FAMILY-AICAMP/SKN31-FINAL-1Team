type GanttExportItem = { title: string; assigneeName: string; start: string; end: string };

// 업무 일정(WBS) 모달의 간트 데이터를 엑셀로 내보낸다. 요구사항정의서 내보내기와
// 동일한 패턴(xlsx 동적 import, 한글 키 → 헤더 자동 생성)을 따른다.
export async function exportGanttExcel(items: GanttExportItem[], scheduleTitle: string) {
  const XLSX = await import("xlsx");

  // 화면의 간트 차트와 동일하게 담당자별로 묶고, 그룹 안에서는 시작일 오름차순으로
  // 정렬한다(같은 담당자의 업무가 뒤섞여 보이지 않도록).
  const sorted = [...items].sort((a, b) => {
    if (a.assigneeName !== b.assigneeName) return a.assigneeName.localeCompare(b.assigneeName, "ko");
    return a.start.localeCompare(b.start);
  });

  const dayCount = (start: string, end: string) =>
    Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 1;

  const rows = sorted.map(item => ({
    "담당자": item.assigneeName,
    "업무명": item.title,
    "시작일": item.start,
    "종료일": item.end,
    "기간(일)": dayCount(item.start, item.end),
  }));

  const sheet = XLSX.utils.json_to_sheet(rows);
  sheet["!cols"] = [{ wch: 14 }, { wch: 36 }, { wch: 12 }, { wch: 12 }, { wch: 10 }];

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, "업무 일정");
  XLSX.writeFile(workbook, `${scheduleTitle}_업무일정.xlsx`);
}
