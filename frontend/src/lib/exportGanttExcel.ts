type GanttExportItem = { id: string; title: string; assigneeName: string; start: string; end: string };

const DAY_MS = 86400000;

function toLocalMidnight(iso: string): number {
  const d = new Date(iso);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

// 화면의 GanttChart와 동일한 규칙: 담당자별로 묶고, 그룹 안에서는 시작일
// 오름차순, 그룹 자체도 그 담당자의 첫 시작일 기준으로 정렬한다.
function groupByAssignee(items: GanttExportItem[]) {
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
    .sort((a, b) => a.firstStart - b.firstStart);
}

// 업무 일정(WBS) 모달의 간트 차트를 화면에 보이는 모습 그대로(담당자 칸 + 날짜별
// 칸에 막대가 병합·색칠된 형태) 실제 엑셀 시트로 만든다. xlsx(SheetJS 커뮤니티
// 버전)는 쓰기 시 셀 배경색/테두리 스타일을 지원하지 않아(유료 Pro 버전 전용
// 기능) 요구사항정의서 내보내기와 달리 exceljs를 쓴다 — 셀 병합·채우기·테두리를
// 그대로 반영할 수 있다.
export async function exportGanttExcel(items: GanttExportItem[], scheduleTitle: string) {
  const ExcelJS = (await import("exceljs")).default;

  const starts = items.map(i => toLocalMidnight(i.start));
  const ends = items.map(i => toLocalMidnight(i.end));
  const rangeStartMs = Math.min(...starts);
  const rangeEndMs = Math.max(...ends);
  const dayCount = Math.max(1, Math.round((rangeEndMs - rangeStartMs) / DAY_MS) + 1);
  const days = Array.from({ length: dayCount }, (_, i) => new Date(rangeStartMs + i * DAY_MS));
  const dayIndexOf = (iso: string) => Math.min(dayCount - 1, Math.max(0, Math.round((toLocalMidnight(iso) - rangeStartMs) / DAY_MS)));
  const fmtHeader = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`;

  const groups = groupByAssignee(items);

  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("간트 차트", { views: [{ state: "frozen", xSplit: 1, ySplit: 1 }] });

  const NAME_COL_WIDTH = 14;
  const DAY_COL_WIDTH = 4;
  sheet.getColumn(1).width = NAME_COL_WIDTH;
  for (let i = 0; i < dayCount; i++) sheet.getColumn(i + 2).width = DAY_COL_WIDTH;

  const THIN = { style: "thin" as const, color: { argb: "FFD0D5DD" } };
  const ALL_BORDERS = { top: THIN, left: THIN, bottom: THIN, right: THIN };

  // 헤더 행: A1은 빈 코너 칸, 이후 날짜 1일당 1칸.
  const headerRow = sheet.getRow(1);
  headerRow.getCell(1).value = "담당자";
  headerRow.getCell(1).font = { bold: true };
  headerRow.getCell(1).fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFF2F4F7" } };
  headerRow.getCell(1).border = ALL_BORDERS;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  days.forEach((d, i) => {
    const cell = headerRow.getCell(i + 2);
    cell.value = fmtHeader(d);
    cell.font = { bold: true, size: 9 };
    cell.alignment = { horizontal: "center" };
    cell.border = ALL_BORDERS;
    const isToday = d.getTime() === today.getTime();
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: isToday ? "FFDCE7FF" : "FFF2F4F7" },
    };
  });

  // 담당자별로 행을 쌓고, 같은 담당자의 연속된 행은 이름 칸을 병합해 화면의
  // "같은 사람이면 이름 한 번만 표시"와 동일하게 만든다.
  let rowIndex = 2;
  const BAR_COLOR = "FF4F46E5";
  for (const group of groups) {
    const groupStartRow = rowIndex;
    for (const item of group.items) {
      const row = sheet.getRow(rowIndex);
      row.height = 20;
      for (let c = 1; c <= dayCount + 1; c++) {
        row.getCell(c).border = ALL_BORDERS;
      }
      const s = dayIndexOf(item.start);
      const e = dayIndexOf(item.end);
      const startCol = s + 2;
      const endCol = e + 2;
      if (endCol > startCol) {
        sheet.mergeCells(rowIndex, startCol, rowIndex, endCol);
      }
      const barCell = row.getCell(startCol);
      barCell.value = item.title;
      barCell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: BAR_COLOR } };
      barCell.font = { color: { argb: "FFFFFFFF" }, size: 9, bold: true };
      barCell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
      rowIndex++;
    }
    const groupEndRow = rowIndex - 1;
    const nameCell = sheet.getCell(groupStartRow, 1);
    nameCell.value = group.name;
    nameCell.font = { bold: true };
    nameCell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
    if (groupEndRow > groupStartRow) {
      sheet.mergeCells(groupStartRow, 1, groupEndRow, 1);
    }
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
