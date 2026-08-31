import type { ReqPriority, ReqSpecDoc, ReqSpecRow } from "@/lib/documentTemplates";
import { Trash2, Plus } from "lucide-react";

const cellInputCls = "w-full bg-black/5 border border-black/10 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40";
const PRIORITY_OPTIONS: ReqPriority[] = ["상", "중", "하"];
const PRIORITY_BADGE_CLASS: Record<ReqPriority, string> = {
  상: "bg-red-100 text-red-700",
  중: "bg-blue-100 text-blue-700",
  하: "bg-gray-100 text-gray-600",
};

export function ReqSpecTemplate({
  doc, title, dateLabel, editable, onChange,
}: {
  doc: ReqSpecDoc; title: string; dateLabel: string;
  editable?: boolean; onChange?: (doc: ReqSpecDoc) => void;
}) {
  const setRow = (i: number, patch: Partial<ReqSpecRow>) => {
    onChange?.({ items: doc.items.map((row, idx) => (idx === i ? { ...row, ...patch } : row)) });
  };
  const addRow = () => {
    onChange?.({
      items: [
        ...doc.items,
        { id: "", category: "", subCategory: "", name: "", description: "", priority: "중", relatedFeature: "", inputOutput: "", acceptanceCriteria: "", note: "" },
      ],
    });
  };
  const removeRow = (i: number) => {
    onChange?.({ items: doc.items.filter((_, idx) => idx !== i) });
  };

  return (
    <div className="bg-white text-black p-10 w-full shadow-sm print:shadow-none print:p-0">
      <div className="text-center border-b-2 border-black pb-6 mb-8">
        <h1 className="text-3xl font-bold">{title} — 요구사항정의서</h1>
        <p className="text-sm text-gray-500 mt-2">작성일 {dateLabel}</p>
      </div>

      {doc.items.length === 0 && !editable ? (
        <p className="text-center text-gray-400 py-10">항목이 없습니다.</p>
      ) : (
        // 좁은 컨테이너(히스토리 모달 등)에 그대로 두면 "기능설명" 칸이 한 글자씩 세로로
        // 찌부러졌었다 — 표에 실제 최소 너비를 줘서, 모자라면 표를 감싼 A4 박스(문서 상세
        // 페이지)나 부모 스크롤 컨테이너가 가로로 스크롤하게 한다. 여기서 자체적으로
        // overflow-x-auto를 또 걸면 스크롤 컨테이너가 이중으로 겹쳐 오히려 스크롤이 먹통처럼
        // 느껴지는 문제가 있었다(실제 보고된 버그) — 그래서 이 div는 폭 강제 목적으로만 둔다.
        <div>
          <table className="w-full min-w-[1500px] print:min-w-0 border-collapse text-sm">
            <thead>
              <tr className="bg-gray-100 border-y-2 border-black">
                <th className="text-left py-2 px-2 font-semibold w-24">요구사항 ID</th>
                <th className="text-left py-2 px-2 font-semibold w-20">대분류</th>
                <th className="text-left py-2 px-2 font-semibold w-20">중분류</th>
                <th className="text-left py-2 px-2 font-semibold w-36">요구사항명</th>
                <th className="text-left py-2 px-2 font-semibold min-w-[240px]">기능설명</th>
                <th className="text-left py-2 px-2 font-semibold w-16">우선순위</th>
                <th className="text-left py-2 px-2 font-semibold w-32">관련 기능</th>
                <th className="text-left py-2 px-2 font-semibold min-w-[200px]">입력/처리/출력</th>
                <th className="text-left py-2 px-2 font-semibold min-w-[220px]">수용 기준</th>
                <th className="text-left py-2 px-2 font-semibold w-28">비고</th>
                {editable && <th className="w-8" />}
              </tr>
            </thead>
            <tbody>
              {doc.items.map((row, i) => (
                <tr key={i} className="border-b border-gray-200 align-top break-inside-avoid">
                  {editable ? (
                    <>
                      <td className="py-1.5 px-1"><input value={row.id} onChange={e => setRow(i, { id: e.target.value })} className={`${cellInputCls} font-mono`} /></td>
                      <td className="py-1.5 px-1"><input value={row.category} onChange={e => setRow(i, { category: e.target.value })} className={cellInputCls} /></td>
                      <td className="py-1.5 px-1"><input value={row.subCategory} onChange={e => setRow(i, { subCategory: e.target.value })} className={cellInputCls} /></td>
                      <td className="py-1.5 px-1"><input value={row.name} onChange={e => setRow(i, { name: e.target.value })} className={`${cellInputCls} font-medium`} /></td>
                      <td className="py-1.5 px-1"><textarea value={row.description} onChange={e => setRow(i, { description: e.target.value })} className={`${cellInputCls} resize-none h-16`} /></td>
                      <td className="py-1.5 px-1">
                        <select value={row.priority ?? "중"} onChange={e => setRow(i, { priority: e.target.value as ReqPriority })} className={cellInputCls}>
                          {PRIORITY_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                      </td>
                      <td className="py-1.5 px-1"><input value={row.relatedFeature ?? ""} onChange={e => setRow(i, { relatedFeature: e.target.value })} className={cellInputCls} /></td>
                      <td className="py-1.5 px-1"><textarea value={row.inputOutput ?? ""} onChange={e => setRow(i, { inputOutput: e.target.value })} className={`${cellInputCls} resize-none h-16`} /></td>
                      <td className="py-1.5 px-1"><textarea value={row.acceptanceCriteria ?? ""} onChange={e => setRow(i, { acceptanceCriteria: e.target.value })} className={`${cellInputCls} resize-none h-16`} /></td>
                      <td className="py-1.5 px-1"><input value={row.note} onChange={e => setRow(i, { note: e.target.value })} className={cellInputCls} /></td>
                      <td className="py-1.5 px-1">
                        <button type="button" onClick={() => removeRow(i)} className="p-1.5 text-red-500 hover:bg-red-50 rounded">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="py-2 px-2 font-mono text-xs">{row.id}</td>
                      <td className="py-2 px-2">{row.category}</td>
                      <td className="py-2 px-2">{row.subCategory}</td>
                      <td className="py-2 px-2 font-medium">{row.name}</td>
                      <td className="py-2 px-2 whitespace-pre-wrap">{row.description}</td>
                      <td className="py-2 px-2">
                        {row.priority && (
                          <span className={`inline-block text-[11px] font-semibold px-1.5 py-0.5 rounded ${PRIORITY_BADGE_CLASS[row.priority]}`}>
                            {row.priority}
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2 text-gray-600">{row.relatedFeature || "-"}</td>
                      <td className="py-2 px-2 whitespace-pre-wrap text-gray-700">{row.inputOutput || "-"}</td>
                      <td className="py-2 px-2 whitespace-pre-wrap text-gray-700">{row.acceptanceCriteria || "-"}</td>
                      <td className="py-2 px-2 text-gray-500">{row.note}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editable && (
        <button type="button" onClick={addRow} className="mt-3 flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
          <Plus className="w-4 h-4" /> 항목 추가
        </button>
      )}
    </div>
  );
}
