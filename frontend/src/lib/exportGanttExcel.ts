type GanttExportItem = {
  id: string; title: string; assigneeName: string; start: string; end: string;
  epicNo: string; epicTitle: string; // 2026-09-22: 화면(GanttChart)의 Epic 열과 동일하게 내보낸다
};

const DAY_MS = 86400000;

function toLocalMidnight(iso: string): number {
  const d = new Date(iso);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

// 화면의 GanttChart와 동일한 규칙: 담당자별로 묶고, 그룹 안에서는 시작일
// 오름차순, 그룹 자체도 그 담당자의 첫 시작일 기준으로 정렬한다. 화면은
// (2026-09-15 AG Grid 전환 이후) 이 그룹을 셀 병합 없이 그대로 펼쳐서 보여주므로
// 여기서도 병합하지 않고 펼친다 — 예전엔 담당자 셀을 병합한 "다른 모양"으로
// 내보내서 화면과 달라 보인다는 지적(2026-09-16)을 받았다.
function flattenByAssignee(items: GanttExportItem[]) {
  const byAssignee = new Map<string, GanttExportItem[]>();
  items.forEach(i => {
    if (!byAssignee.has(i.assigneeName)) byAssignee.set(i.assigneeName, []);
    byAssignee.get(i.assigneeName)!.push(i);
  });
  return Array.from(byAssignee.entries())
    .map(([name, personItems]) => {
      const sorted = [...personItems].sort((a, b) => toLocalMidnight(a.start) - toLocalMidnight(b.start));
      return { name, items: sorted, firstStart: toLocalMidnight(sorted[0].start) };
    })
    .sort((a, b) => a.firstStart - b.firstStart)
    .flatMap(g => g.items.map(item => ({ ...item, assigneeName: g.name })));
}

// 업무 일정(WBS) 모달의 간트 차트(GanttChart, documents/page.tsx)를 화면에 보이는
// 모습 그대로 엑셀로 만든다 — 작업명/담당자 열이 각 행마다 그대로 나오고(병합
// 없음), 날짜 칸은 하루 단위로 칠해지며 주말은 실제 업무가 없는 날이라 칠하지
// 않는다(화면과 동일, 2026-09-15 결정). xlsx(SheetJS 커뮤니티 버전)는 쓰기 시 셀
// 배경색/병합을 지원하지 않아(유료 Pro 버전 전용) exceljs를 쓴다.
export async function exportGanttExcel(items: GanttExportItem[], scheduleTitle: string) {
  const ExcelJS = (await import("exceljs")).default;

  const starts = items.map(i => toLocalMidnight(i.start));
  const ends = items.map(i => toLocalMidnight(i.end));
  const rangeStartMs = Math.min(...starts);
  const rangeEndMs = Math.max(...ends);
  const dayCount = Math.max(1, Math.round((rangeEndMs - rangeStartMs) / DAY_MS) + 1);
  const days = Array.from({ length: dayCount }, (_, i) => new Date(rangeStartMs + i * DAY_MS));
  const dayIndexOf = (iso: string) => Math.min(dayCount - 1, Math.max(0, Math.round((toLocalMidnight(iso) - rangeStartMs) / DAY_MS)));

  const rows = flattenByAssignee(items);

  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("간트 차트", { views: [{ state: "frozen", xSplit: 3, ySplit: 2 }] });

  const EPIC_COL_WIDTH = 22;
  const TITLE_COL_WIDTH = 26;
  const NAME_COL_WIDTH = 12;
  const DAY_COL_WIDTH = 4;
  sheet.getColumn(1).width = EPIC_COL_WIDTH;
  sheet.getColumn(2).width = TITLE_COL_WIDTH;
  sheet.getColumn(3).width = NAME_COL_WIDTH;
  for (let i = 0; i < dayCount; i++) sheet.getColumn(i + 4).width = DAY_COL_WIDTH;

  const THIN = { style: "thin" as const, color: { argb: "FFD0D5DD" } };
  const ALL_BORDERS = { top: THIN, left: THIN, bottom: THIN, right: THIN };
  const HEADER_FILL = { type: "pattern" as const, pattern: "solid" as const, fgColor: { argb: "FFF2F4F7" } };
  const TODAY_FILL = { type: "pattern" as const, pattern: "solid" as const, fgColor: { argb: "FFDCE7FF" } };

  // 화면(GanttChart)과 동일하게 2단 헤더 — 위쪽은 월(月) 그룹, 아래쪽은 일(日)
  // 숫자. 작업명/담당자 칸은 두 헤더 행을 세로로 합쳐 한 칸처럼 보이게 한다.
  const monthRow = sheet.getRow(1);
  const dayRow = sheet.getRow(2);

  monthRow.getCell(1).value = "Epic";
  monthRow.getCell(2).value = "작업명";
  monthRow.getCell(3).value = "담당자";
  sheet.mergeCells(1, 1, 2, 1);
  sheet.mergeCells(1, 2, 2, 2);
  sheet.mergeCells(1, 3, 2, 3);
  [1, 2, 3].forEach(c => {
    const cell = monthRow.getCell(c);
    cell.font = { bold: true };
    cell.fill = HEADER_FILL;
    cell.border = ALL_BORDERS;
    cell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
    dayRow.getCell(c).border = ALL_BORDERS;
  });

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  let monthGroupStartCol = 4;
  days.forEach((d, i) => {
    const col = i + 4;
    const isWeekend = d.getDay() === 0 || d.getDay() === 6;
    const isToday = d.getTime() === today.getTime();
    const isMonthStart = d.getDate() === 1;
    const nextIsNewMonth = i === dayCount - 1 || days[i + 1].getMonth() !== d.getMonth();

    if (isMonthStart && i > 0) monthGroupStartCol = col;
    if (nextIsNewMonth) {
      if (col > monthGroupStartCol) sheet.mergeCells(1, monthGroupStartCol, 1, col);
      const monthCell = monthRow.getCell(monthGroupStartCol);
      monthCell.value = `${d.getMonth() + 1}월`;
      monthCell.font = { bold: true, size: 10 };
      monthCell.alignment = { horizontal: "center", vertical: "middle" };
      monthCell.fill = HEADER_FILL;
      for (let c = monthGroupStartCol; c <= col; c++) monthRow.getCell(c).border = ALL_BORDERS;
    }

    const dayCell = dayRow.getCell(col);
    dayCell.value = d.getDate();
    dayCell.font = { bold: true, size: 9, color: { argb: isWeekend ? "FFDC2626" : "FF000000" } };
    dayCell.alignment = { horizontal: "center" };
    dayCell.border = {
      ...ALL_BORDERS,
      left: isMonthStart ? { style: "medium", color: { argb: "FF94A3B8" } } : THIN,
    };
    dayCell.fill = isToday ? TODAY_FILL : HEADER_FILL;
  });

  // 본문 — 화면과 동일하게 작업명·담당자를 매 행 그대로 반복해서 쓰고(병합 없음),
  // 날짜 칸은 하루 단위로 색칠한다. 주말 칸은 실제 업무가 없는 날이라 절대
  // 칠하지 않는다(화면의 cellStyle과 동일한 규칙).
  const BAR_COLOR = "FF4F46E5";
  let rowIndex = 3;
  for (const item of rows) {
    const row = sheet.getRow(rowIndex);
    row.height = 20;

    const epicCell = row.getCell(1);
    epicCell.value = [item.epicNo, item.epicTitle].filter(Boolean).join(" · ");
    epicCell.font = { size: 9, color: { argb: "FF667085" } };
    epicCell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
    epicCell.border = ALL_BORDERS;

    const titleCell = row.getCell(2);
    titleCell.value = item.title;
    titleCell.font = { bold: true, size: 9 };
    titleCell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
    titleCell.border = ALL_BORDERS;

    const nameCell = row.getCell(3);
    nameCell.value = item.assigneeName;
    nameCell.font = { size: 9 };
    nameCell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
    nameCell.border = ALL_BORDERS;

    const s = dayIndexOf(item.start);
    const e = dayIndexOf(item.end);
    for (let i = 0; i < dayCount; i++) {
      const col = i + 4;
      const cell = row.getCell(col);
      cell.border = ALL_BORDERS;
      const isWeekend = days[i].getDay() === 0 || days[i].getDay() === 6;
      if (!isWeekend && s <= i && i <= e) {
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: BAR_COLOR } };
      }
    }
    rowIndex++;
  }

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${scheduleTitle}_업무일정.xlsx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
