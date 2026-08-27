import type { ReqSpecDoc, ReqSpecRow } from "@/lib/documentTemplates";
import { Trash2, Plus } from "lucide-react";

const cellInputCls = "w-full bg-black/5 border border-black/10 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40";

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
    onChange?.({ items: [...doc.items, { id: "", category: "", subCategory: "", name: "", description: "", note: "" }] });
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
        // 찌부러졌었다 — 표에 실제 최소 너비를 줘서, 모자라면 표 전체가 가로 스크롤되게 한다.
        <div className="overflow-x-auto print:overflow-visible">
          <table className="w-full min-w-[880px] print:min-w-0 border-collapse text-sm">
            <thead>
              <tr className="bg-gray-100 border-y-2 border-black">
                <th className="text-left py-2 px-2 font-semibold w-28">요구사항 ID</th>
                <th className="text-left py-2 px-2 font-semibold w-24">대분류</th>
                <th className="text-left py-2 px-2 font-semibold w-24">중분류</th>
                <th className="text-left py-2 px-2 font-semibold w-40">요구사항명</th>
                <th className="text-left py-2 px-2 font-semibold min-w-[280px]">기능설명</th>
                <th className="text-left py-2 px-2 font-semibold w-32">비고</th>
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
                      <td className="py-1.5 px-1"><textarea value={row.description} onChange={e => setRow(i, { description: e.target.value })} className={`${cellInputCls} resize-none h-14`} /></td>
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
