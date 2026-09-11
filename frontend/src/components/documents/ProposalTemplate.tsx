import { useState } from "react";
import { ChevronDown } from "lucide-react";
import DOMPurify from "isomorphic-dompurify";
import type { ProposalDoc } from "@/lib/documentTemplates";

// 섹션별 근거자료 — 각 섹션(1~7번) 바로 아래에 개별로 붙는다(사용자 요청, 문서 맨 아래에
// 하나로 모아두던 이전 방식은 폐기). ProposalDoc의 7개 섹션 필드명을 그대로 근거 데이터의
// 표준 키로 쓴다 — 백엔드가 evidence_data를 채울 때 이 이름으로 저장하면 된다.
export type ProposalEvidence = Partial<Record<
  "projectOverview" | "problemDefinition" | "projectGoals" | "target" | "features" | "techStackConstraints" | "finalDecisions",
  string
>>;

const inputCls = "w-full bg-black/5 border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40";

// 백엔드(meetings/views.py)가 AI가 만든 content_html을 <p>/<strong>/<ul>/<li> 4종류
// 태그로만 제한해 저장하고, 회의록에서 온 원문 텍스트는 저장 전 escape()를 거친다고
// 확인받았다(팀원 공유 내용) — 그래도 프론트에서 dangerouslySetInnerHTML을 쓰는 이상
// 그 4종류 외의 태그/속성은 실제 HTML 파서 기반 라이브러리(DOMPurify)로 한 번 더
// 걸러낸다. 정규식으로 직접 태그를 걷어내는 방식은 중첩/손상된 태그나 인코딩 트릭에
// 뚫릴 수 있는 알려진 안티패턴이라 피했다.
function sanitizeRestrictedHtml(html: string): string {
  if (!html) return html;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["p", "strong", "ul", "li"],
    ALLOWED_ATTR: [],
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
  doc, title, dateLabel, editable, onChange, periodEditable, onPeriodChange, evidence,
}: {
  doc: ProposalDoc; title: string; dateLabel: string;
  editable?: boolean; onChange?: (doc: ProposalDoc) => void;
  // 기간은 본문 섹션들과 달리 "직접 수정" 모드에 들어가지 않아도 항상 바로 입력할 수 있어야
  // 한다(회의록에 범위가 없으면 AI가 채울 수 없는 값이라 매번 수정 모드까지 탈 필요가 없음).
  // 그래서 본문 편집 여부(editable)와 별도로 periodEditable을 둔다.
  periodEditable?: boolean; onPeriodChange?: (period: { start: string; end: string }) => void;
  // 섹션별 근거자료 — 없으면(백엔드 미채움) 각 섹션 아래에 "아직 근거 자료가 없습니다"만 보임.
  // 전달 안 하면(reqSpec 탭의 작은 참고 박스 등) 근거자료 토글 자체를 안 보여준다.
  evidence?: ProposalEvidence;
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

      <Section num="1" title="프로젝트 개요" evidence={evidence} evidenceKey="projectOverview">
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

      <Section num="2" title="핵심 목표" evidence={evidence} evidenceKey="problemDefinition">
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

      <Section num="3" title="세부 목표 및 문제 정의" evidence={evidence} evidenceKey="projectGoals">
        {editable ? (
          <textarea
            value={doc.projectGoals}
            onChange={e => set("projectGoals", e.target.value)}
            placeholder="세부 목표 및 문제 정의를 입력하세요."
            className={`${inputCls} h-24 resize-none whitespace-pre-wrap`}
          />
        ) : (
          <RichText html={doc.projectGoals} />
        )}
      </Section>

      <Section num="4" title="대상 사용자" evidence={evidence} evidenceKey="target">
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

      <Section num="5" title="주요 기능" evidence={evidence} evidenceKey="features">
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

      <Section num="6" title="기술 스택 및 제약사항" evidence={evidence} evidenceKey="techStackConstraints">
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

      <Section num="7" title="최종 결정사항" evidence={evidence} evidenceKey="finalDecisions">
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

function Section({
  num, title, children, evidence, evidenceKey,
}: {
  num: string; title: string; children: React.ReactNode;
  // evidence가 아예 안 넘어오면(예: reqSpec 탭의 작은 참고 박스) 근거자료 토글 자체를 안 보여준다.
  // evidence 객체는 있는데 이 섹션 키 값이 없으면 "아직 근거 자료가 없습니다"를 보여준다.
  evidence?: ProposalEvidence; evidenceKey?: keyof ProposalEvidence;
}) {
  return (
    <div className="mb-7 break-inside-avoid">
      <h2 className="text-lg font-bold border-l-4 border-primary pl-3 mb-3">{num}. {title}</h2>
      <div className="pl-3">{children}</div>
      {evidence && evidenceKey && (
        <div className="pl-3 mt-2 print:hidden">
          <SectionEvidence text={evidence[evidenceKey]} />
        </div>
      )}
    </div>
  );
}

// 섹션별 근거자료 토글 — 기본은 접힘(사용자 요청), 제목 클릭으로 펼침. PDF 인쇄에는 위
// print:hidden으로 이미 빠지고, PPTX 내보내기는 ProposalDoc(evidence 없는 타입)만 읽으므로
// 애초에 포함되지 않는다.
function SectionEvidence({ text }: { text?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 text-gray-500 font-semibold hover:text-gray-700 transition-colors"
      >
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${!open ? "-rotate-90" : ""}`} />
        근거자료
      </button>
      {open && (
        <div className="mt-1.5 p-3 rounded-lg bg-gray-50 border border-gray-200 text-gray-600 whitespace-pre-wrap">
          {text && text.trim() ? text : "아직 근거 자료가 없습니다."}
        </div>
      )}
    </div>
  );
}
