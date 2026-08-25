import type { ProposalDoc, ProposalFeature, ProposalMilestone } from "@/lib/documentTemplates";
import { Trash2, Plus } from "lucide-react";

const inputCls = "w-full bg-black/5 border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40";

export function ProposalTemplate({
  doc, title, dateLabel, editable, onChange,
}: {
  doc: ProposalDoc; title: string; dateLabel: string;
  editable?: boolean; onChange?: (doc: ProposalDoc) => void;
}) {
  const set = <K extends keyof ProposalDoc>(key: K, value: ProposalDoc[K]) => onChange?.({ ...doc, [key]: value });

  const setFeature = (i: number, patch: Partial<ProposalFeature>) => {
    set("features", doc.features.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
  };
  const addFeature = () => set("features", [...(doc.features ?? []), { name: "", description: "" }]);
  const removeFeature = (i: number) => set("features", doc.features.filter((_, idx) => idx !== i));

  const setMilestone = (i: number, patch: Partial<ProposalMilestone>) => {
    set("milestones", doc.milestones.map((m, idx) => (idx === i ? { ...m, ...patch } : m)));
  };
  const addMilestone = () => set("milestones", [...(doc.milestones ?? []), { name: "", date: "" }]);
  const removeMilestone = (i: number) => set("milestones", doc.milestones.filter((_, idx) => idx !== i));

  return (
    <div className="bg-white text-black p-10 w-full shadow-sm print:shadow-none print:p-0">
      <div className="text-center border-b-2 border-black pb-6 mb-8">
        <h1 className="text-3xl font-bold">{title}</h1>
        <p className="text-sm text-gray-500 mt-2">작성일 {dateLabel}</p>
        {/* 원본에 명시된 프로젝트 기간 — 업무분배 탭에서 오늘 날짜 대신 이 시작일부터 WBS 일정을 잡는 데 쓰인다 */}
        {editable ? (
          <div className="flex items-center justify-center gap-2 mt-3 text-sm">
            <span className="text-gray-500">프로젝트 기간</span>
            <input
              type="date"
              value={doc.projectPeriod?.start ?? ""}
              onChange={e => set("projectPeriod", { start: e.target.value, end: doc.projectPeriod?.end ?? "" })}
              className={`${inputCls} w-auto`}
            />
            <span className="text-gray-400">~</span>
            <input
              type="date"
              value={doc.projectPeriod?.end ?? ""}
              onChange={e => set("projectPeriod", { start: doc.projectPeriod?.start ?? "", end: e.target.value })}
              className={`${inputCls} w-auto`}
            />
          </div>
        ) : (doc.projectPeriod?.start || doc.projectPeriod?.end) ? (
          <p className="text-sm text-gray-500 mt-1">
            프로젝트 기간 {doc.projectPeriod.start || "?"} ~ {doc.projectPeriod.end || "?"}
          </p>
        ) : null}
      </div>

      <Section num="1" title="배경 및 목적">
        {editable ? (
          <textarea
            value={doc.background}
            onChange={e => set("background", e.target.value)}
            className={`${inputCls} h-24 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.background || "-"}</p>
        )}
      </Section>

      <Section num="2" title="타겟 사용자">
        {editable ? (
          <textarea
            value={doc.target}
            onChange={e => set("target", e.target.value)}
            className={`${inputCls} h-20 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.target || "-"}</p>
        )}
      </Section>

      <Section num="3" title="주요 기능">
        {editable ? (
          <div className="space-y-3">
            {doc.features?.map((f, i) => (
              <div key={i} className="flex gap-2 items-start p-3 rounded-lg bg-black/[0.03] border border-black/10">
                <div className="flex-1 space-y-2">
                  <input
                    value={f.name}
                    onChange={e => setFeature(i, { name: e.target.value })}
                    placeholder="기능명"
                    className={`${inputCls} font-semibold`}
                  />
                  <textarea
                    value={f.description}
                    onChange={e => setFeature(i, { description: e.target.value })}
                    placeholder="설명"
                    className={`${inputCls} h-16 resize-none`}
                  />
                </div>
                <button type="button" onClick={() => removeFeature(i)} className="p-2 text-red-500 hover:bg-red-50 rounded-lg shrink-0">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={addFeature} className="flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
              <Plus className="w-4 h-4" /> 기능 추가
            </button>
          </div>
        ) : doc.features?.length ? (
          <ol className="space-y-3 list-decimal list-inside">
            {doc.features.map((f, i) => (
              <li key={i}>
                <span className="font-semibold">{f.name}</span>
                <p className="text-sm text-gray-700 mt-0.5 ml-5 whitespace-pre-wrap">{f.description}</p>
              </li>
            ))}
          </ol>
        ) : <p className="text-gray-400">-</p>}
      </Section>

      <Section num="4" title="기대 효과">
        {editable ? (
          <textarea
            value={doc.expectedEffect}
            onChange={e => set("expectedEffect", e.target.value)}
            className={`${inputCls} h-20 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.expectedEffect || "-"}</p>
        )}
      </Section>

      {(editable || doc.milestones?.length > 0) && (
        <Section num="5" title="일정 / 마일스톤">
          {editable ? (
            <div className="space-y-2">
              {doc.milestones?.map((m, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input
                    value={m.name}
                    onChange={e => setMilestone(i, { name: e.target.value })}
                    placeholder="마일스톤"
                    className={`${inputCls} flex-1`}
                  />
                  <input
                    value={m.date}
                    onChange={e => setMilestone(i, { date: e.target.value })}
                    placeholder="시기"
                    className={`${inputCls} w-40`}
                  />
                  <button type="button" onClick={() => removeMilestone(i)} className="p-2 text-red-500 hover:bg-red-50 rounded-lg shrink-0">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button type="button" onClick={addMilestone} className="flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
                <Plus className="w-4 h-4" /> 마일스톤 추가
              </button>
            </div>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-black">
                  <th className="text-left py-2 font-semibold">마일스톤</th>
                  <th className="text-left py-2 font-semibold w-40">시기</th>
                </tr>
              </thead>
              <tbody>
                {doc.milestones.map((m, i) => (
                  <tr key={i} className="border-b border-gray-200">
                    <td className="py-2">{m.name}</td>
                    <td className="py-2">{m.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      )}
    </div>
  );
}

function Section({ num, title, children }: { num: string; title: string; children: React.ReactNode }) {
  return (
    <div className="mb-7 break-inside-avoid">
      <h2 className="text-lg font-bold border-l-4 border-primary pl-3 mb-3">{num}. {title}</h2>
      <div className="pl-3">{children}</div>
    </div>
  );
}
