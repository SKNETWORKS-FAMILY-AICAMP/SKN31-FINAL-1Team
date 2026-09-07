import type { ProposalDoc } from "@/lib/documentTemplates";

const inputCls = "w-full bg-black/5 border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40";

// 백엔드(meetings/views.py)가 AI가 만든 content_html을 <p>/<strong>/<ul>/<li> 4종류
// 태그로만 제한해 저장하고, 회의록에서 온 원문 텍스트는 저장 전 escape()를 거친다고
// 확인받았다(팀원 공유 내용) — 그래도 프론트에서 dangerouslySetInnerHTML을 쓰는 이상
// 그 4종류 외의 태그/모든 속성(예: onerror, href javascript:)은 한 번 더 걸러낸다.
const ALLOWED_TAGS = new Set(["p", "strong", "ul", "li"]);
function sanitizeRestrictedHtml(html: string): string {
  if (!html) return html;
  return html
    .replace(/<(script|style)[\s\S]*?<\/\1>/gi, "")
    .replace(/<\/?([a-zA-Z0-9]+)([^>]*)>/g, (match, tag: string) => {
      const lower = tag.toLowerCase();
      if (!ALLOWED_TAGS.has(lower)) return "";
      return match.startsWith("</") ? `</${lower}>` : `<${lower}>`;
    });
}

function RichText({ html }: { html: string }) {
  if (!html) return <p className="leading-relaxed">-</p>;
  return (
    <div
      className="leading-relaxed [&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-bold [&_ul]:list-disc [&_ul]:pl-5 [&_li]:mb-1"
      dangerouslySetInnerHTML={{ __html: sanitizeRestrictedHtml(html) }}
    />
  );
}

export function ProposalTemplate({
  doc, title, dateLabel, editable, onChange, periodEditable, onPeriodChange,
}: {
  doc: ProposalDoc; title: string; dateLabel: string;
  editable?: boolean; onChange?: (doc: ProposalDoc) => void;
  // 기간은 본문 섹션들과 달리 "직접 수정" 모드에 들어가지 않아도 항상 바로 입력할 수 있어야
  // 한다(회의록에 범위가 없으면 AI가 채울 수 없는 값이라 매번 수정 모드까지 탈 필요가 없음).
  // 그래서 본문 편집 여부(editable)와 별도로 periodEditable을 둔다.
  periodEditable?: boolean; onPeriodChange?: (period: { start: string; end: string }) => void;
}) {
  const set = <K extends keyof ProposalDoc>(key: K, value: ProposalDoc[K]) => onChange?.({ ...doc, [key]: value });
  const setPeriod = (period: { start: string; end: string }) => {
    onPeriodChange?.(period);
    if (editable) set("projectPeriod", period);
  };

  return (
    <div className="bg-white text-black p-10 w-full shadow-sm print:shadow-none print:p-0">
      <div className="text-center border-b-2 border-black pb-6 mb-8">
        <h1 className="text-3xl font-bold">{title}</h1>
        <p className="text-sm text-gray-500 mt-2">작성일 {dateLabel}</p>
        {editable || periodEditable ? (
          <div className="flex items-center justify-center gap-2 mt-3 text-sm">
            <span className="text-gray-500">프로젝트 기간</span>
            <input
              type="date"
              value={doc.projectPeriod?.start ?? ""}
              onChange={e => setPeriod({ start: e.target.value, end: doc.projectPeriod?.end ?? "" })}
              className={`${inputCls} w-auto`}
            />
            <span className="text-gray-400">~</span>
            <input
              type="date"
              value={doc.projectPeriod?.end ?? ""}
              onChange={e => setPeriod({ start: doc.projectPeriod?.start ?? "", end: e.target.value })}
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
          <RichText html={doc.projectOverview} />
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
          <RichText html={doc.problemDefinition} />
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
          <RichText html={doc.target} />
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
          <RichText html={doc.features} />
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
          <RichText html={doc.userScenario} />
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
          <RichText html={doc.techStackConstraints} />
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
          <RichText html={doc.finalDecisions} />
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
