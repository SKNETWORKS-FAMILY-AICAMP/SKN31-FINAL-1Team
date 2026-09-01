import type { ProposalDoc } from "@/lib/documentTemplates";

const inputCls = "w-full bg-black/5 border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40";

export function ProposalTemplate({
  doc, title, dateLabel, editable, onChange,
}: {
  doc: ProposalDoc; title: string; dateLabel: string;
  editable?: boolean; onChange?: (doc: ProposalDoc) => void;
}) {
  const set = <K extends keyof ProposalDoc>(key: K, value: ProposalDoc[K]) => onChange?.({ ...doc, [key]: value });

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
          <textarea
            value={doc.features}
            onChange={e => set("features", e.target.value)}
            placeholder="기능명과 설명을 자유롭게 작성하세요 (줄바꿈으로 구분)"
            className={`${inputCls} h-28 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.features || "-"}</p>
        )}
      </Section>

      <Section num="5" title="사용자 시나리오">
        {editable ? (
          <textarea
            value={doc.userScenario}
            onChange={e => set("userScenario", e.target.value)}
            placeholder="시나리오 단계를 자유롭게 작성하세요 (줄바꿈으로 구분)"
            className={`${inputCls} h-24 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.userScenario || "-"}</p>
        )}
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
          <textarea
            value={doc.finalDecisions}
            onChange={e => set("finalDecisions", e.target.value)}
            placeholder="결정 사항을 자유롭게 작성하세요 (줄바꿈으로 구분)"
            className={`${inputCls} h-24 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{doc.finalDecisions || "-"}</p>
        )}
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
