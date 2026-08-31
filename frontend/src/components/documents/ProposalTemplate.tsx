import { stripLeadingNumber, type FeaturePriority, type ProposalDoc, type ProposalFeature } from "@/lib/documentTemplates";
import { Trash2, Plus } from "lucide-react";

const inputCls = "w-full bg-black/5 border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40";

const PRIORITY_OPTIONS: FeaturePriority[] = ["필수", "권장", "선택"];
const PRIORITY_BADGE_CLASS: Record<FeaturePriority, string> = {
  필수: "bg-red-100 text-red-700",
  권장: "bg-blue-100 text-blue-700",
  선택: "bg-gray-100 text-gray-600",
};

function PriorityBadge({ priority }: { priority?: FeaturePriority }) {
  const p = priority ?? "권장";
  return (
    <span className={`inline-block text-[11px] font-semibold px-1.5 py-0.5 rounded ${PRIORITY_BADGE_CLASS[p]}`}>
      {p}
    </span>
  );
}

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

  // 사용자 시나리오 / 최종 결정사항은 둘 다 "단순 문자열 목록"이라 같은 add/remove/set 패턴을 재사용한다.
  const setListItem = (key: "userScenario" | "finalDecisions", i: number, value: string) => {
    set(key, doc[key].map((s, idx) => (idx === i ? value : s)));
  };
  const addListItem = (key: "userScenario" | "finalDecisions") => set(key, [...(doc[key] ?? []), ""]);
  const removeListItem = (key: "userScenario" | "finalDecisions", i: number) =>
    set(key, doc[key].filter((_, idx) => idx !== i));

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

      <Section num="1" title="프로젝트 개요">
        {editable ? (
          <textarea
            value={doc.projectOverview}
            onChange={e => set("projectOverview", e.target.value)}
            className={`${inputCls} h-24 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.projectOverview || "-"}</p>
        )}
      </Section>

      <Section num="2" title="문제 정의">
        {editable ? (
          <textarea
            value={doc.problemDefinition}
            onChange={e => set("problemDefinition", e.target.value)}
            className={`${inputCls} h-24 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.problemDefinition || "-"}</p>
        )}
      </Section>

      <Section num="3" title="대상 사용자">
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

      <Section num="4" title="주요 기능">
        {editable ? (
          <div className="space-y-3">
            {doc.features?.map((f, i) => (
              <div key={i} className="flex gap-2 items-start p-3 rounded-lg bg-black/[0.03] border border-black/10">
                <div className="flex-1 space-y-2">
                  <div className="flex gap-2 items-center">
                    <input
                      value={f.name}
                      onChange={e => setFeature(i, { name: e.target.value })}
                      placeholder="기능명"
                      className={`${inputCls} font-semibold`}
                    />
                    <select
                      value={f.priority ?? "권장"}
                      onChange={e => setFeature(i, { priority: e.target.value as FeaturePriority })}
                      className={`${inputCls} w-24! shrink-0`}
                    >
                      {PRIORITY_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </div>
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
                <span className="font-semibold">{f.name}</span>{" "}
                <PriorityBadge priority={f.priority} />
                <p className="text-sm text-gray-700 mt-0.5 ml-5 whitespace-pre-wrap">{f.description}</p>
              </li>
            ))}
          </ol>
        ) : <p className="text-gray-400">-</p>}
      </Section>

      <Section num="5" title="사용자 시나리오">
        {editable ? (
          <div className="space-y-2">
            {doc.userScenario?.map((step, i) => (
              <div key={i} className="flex gap-2 items-center">
                <span className="text-sm text-gray-400 w-5 shrink-0 text-right">{i + 1}.</span>
                <input
                  value={stripLeadingNumber(step)}
                  onChange={e => setListItem("userScenario", i, e.target.value)}
                  placeholder="시나리오 단계"
                  className={inputCls}
                />
                <button type="button" onClick={() => removeListItem("userScenario", i)} className="p-2 text-red-500 hover:bg-red-50 rounded-lg shrink-0">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => addListItem("userScenario")} className="flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
              <Plus className="w-4 h-4" /> 단계 추가
            </button>
          </div>
        ) : doc.userScenario?.length ? (
          <ol className="space-y-1.5 list-decimal list-inside">
            {doc.userScenario.map((step, i) => (
              <li key={i} className="whitespace-pre-wrap">{stripLeadingNumber(step)}</li>
            ))}
          </ol>
        ) : <p className="text-gray-400">-</p>}
      </Section>

      <Section num="6" title="기술 스택 및 제약사항">
        {editable ? (
          <textarea
            value={doc.techStackConstraints}
            onChange={e => set("techStackConstraints", e.target.value)}
            placeholder="기술 스택, 플랫폼, 연동 대상, 제약사항 등 (없으면 비워두세요)"
            className={`${inputCls} h-20 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.techStackConstraints || "-"}</p>
        )}
      </Section>

      <Section num="7" title="최종 결정사항">
        {editable ? (
          <div className="space-y-2">
            {doc.finalDecisions?.map((decision, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input
                  value={decision}
                  onChange={e => setListItem("finalDecisions", i, e.target.value)}
                  placeholder="결정 사항"
                  className={inputCls}
                />
                <button type="button" onClick={() => removeListItem("finalDecisions", i)} className="p-2 text-red-500 hover:bg-red-50 rounded-lg shrink-0">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => addListItem("finalDecisions")} className="flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
              <Plus className="w-4 h-4" /> 결정사항 추가
            </button>
          </div>
        ) : doc.finalDecisions?.length ? (
          <ul className="space-y-1.5">
            {doc.finalDecisions.map((decision, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-black shrink-0 mt-2" />
                <span className="whitespace-pre-wrap">{decision}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-gray-400">-</p>}
      </Section>
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
