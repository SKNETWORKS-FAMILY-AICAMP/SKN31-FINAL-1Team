"use client";

import { useState } from "react";
import { Settings as SettingsIcon, HelpCircle, Mail, ChevronDown, FileText, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { TERMS_ARTICLES, TERMS_EFFECTIVE_DATE, PRIVACY_SECTIONS, PRIVACY_EFFECTIVE_DATE } from "@/lib/legalContent";

const SUPPORT_EMAIL = "kimjae9360@gmail.com";

// 사용방법 위주 FAQ — 실제 파이프라인/화면 동작을 근거로 작성(일반적인 문구 아님)
const FAQ_ITEMS = [
  { q: "문서는 어떻게 만드나요?", a: "문서생성 페이지에서 \"새 회의록/문서\"로 회의록을 등록하면, AI가 기획서를 생성합니다. PM 검토·승인을 거치면 요구사항정의서 생성 → 승인 → 업무 자동 추출까지 이어집니다." },
  { q: "업무 담당자는 어떻게 배정하나요?", a: "요구사항정의서가 승인되면 문서생성의 \"업무 배분\" 탭에서 AI 추천을 받아 배정하거나, 업무관리 칸반에서 직접 담당자를 지정해 배분 승인을 요청할 수 있습니다." },
  { q: "\"배분승인대기\"는 무슨 뜻인가요?", a: "업무 완료 승인이 아니라, 담당자 지정에 대한 PM 승인 대기 상태입니다. PM이 승인해야 그 업무가 \"진행 중\"으로 넘어갑니다." },
  { q: "알림은 어디서 확인하나요?", a: "모든 화면 상단 우측 종 아이콘에서 확인할 수 있습니다. 안읽음이 있으면 아이콘이 주황색으로 바뀌고, 항목을 클릭하면 관련 화면으로 이동하며 읽음 처리됩니다." },
  { q: "PM과 일반유저는 권한이 어떻게 다른가요?", a: "PM은 프로젝트 생성, 문서·업무 배분 승인, 직원관리 등을 할 수 있습니다. 일반유저는 본인이 담당한 업무 위주로 진행 상황을 관리합니다." },
  { q: "비밀번호를 잊어버렸어요.", a: "현재는 자가 비밀번호 재설정 기능이 없습니다. 소속 PM(관리자)에게 계정 초기화를 요청해 주세요." },
];

export default function SettingsPage() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [openLegal, setOpenLegal] = useState<"terms" | "privacy" | null>(null);

  return (
    <div className="w-full max-w-3xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-muted-foreground mb-1">
          <SettingsIcon className="w-5 h-5 text-primary" />
          <h1 className="text-3xl font-black text-foreground tracking-tight">설정</h1>
        </div>
        <p className="text-muted-foreground">
          자주 묻는 질문과 법적 고지를 확인합니다.
        </p>
      </div>

      {/* "반려 패턴 분석"(AI가 반려 사유를 모아 패턴/개선안을 제안하는 기능) 섹션은 제거했다 —
          heyzzabi2 시절 /api/projects/{id}/reject-insights 라우트를 그대로 호출하고 있었는데,
          이 프로젝트의 Django 백엔드엔 그런 엔드포인트/AI 파이프라인이 아예 없다. 버튼만 있고
          누르면 항상 실패하는 상태였다 — 만들려면 별도 기능 개발이 필요해서 지금은 뺀다. */}

      {/* 고객지원 */}
      <section className="glass rounded-2xl border border-border p-6 space-y-4">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-primary" /> 고객지원
          </h2>
          <p className="text-xs text-muted-foreground mt-1">자주 묻는 질문과 사용법입니다. 해결되지 않으면 아래 문의 메일로 연락해 주세요.</p>
        </div>

        <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
          {FAQ_ITEMS.map((item, i) => (
            <div key={i}>
              <button
                onClick={() => setOpenFaq(v => (v === i ? null : i))}
                className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
              >
                <span className="text-sm font-semibold">{item.q}</span>
                <ChevronDown className={cn("w-4 h-4 text-muted-foreground shrink-0 transition-transform", openFaq === i && "rotate-180")} />
              </button>
              {openFaq === i && (
                <p className="px-4 pb-4 text-sm text-muted-foreground leading-relaxed">{item.a}</p>
              )}
            </div>
          ))}
        </div>

        <a
          href={`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent("[헤이짜비] 오류/문의")}`}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 transition-colors w-fit"
        >
          <Mail className="w-4 h-4" /> 오류 문의하기 ({SUPPORT_EMAIL})
        </a>
      </section>

      {/* 법적 고지 — 이용약관/개인정보처리방침도 FAQ와 동일하게 눌러서 펼쳐본다.
          전체 내용은 /settings/legalContent.ts를 공유해서 /settings/terms, /settings/privacy
          단독 페이지(직접 링크 공유용)와 문구가 어긋나지 않게 한다. */}
      <section className="glass rounded-2xl border border-border p-6 space-y-3">
        <h2 className="text-lg font-bold">법적 고지</h2>
        <div className="border border-border rounded-xl overflow-hidden divide-y divide-border">
          <div>
            <button
              onClick={() => setOpenLegal(v => (v === "terms" ? null : "terms"))}
              className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <span className="flex items-center gap-2 text-sm font-semibold">
                <FileText className="w-4 h-4 text-muted-foreground" /> 이용약관
              </span>
              <ChevronDown className={cn("w-4 h-4 text-muted-foreground shrink-0 transition-transform", openLegal === "terms" && "rotate-180")} />
            </button>
            {openLegal === "terms" && (
              <div className="px-4 pb-4 space-y-4">
                <p className="text-xs text-muted-foreground">시행일: {TERMS_EFFECTIVE_DATE}</p>
                {TERMS_ARTICLES.map(a => (
                  <div key={a.title}>
                    <h3 className="font-bold text-xs mb-1">{a.title}</h3>
                    <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">{a.body}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <button
              onClick={() => setOpenLegal(v => (v === "privacy" ? null : "privacy"))}
              className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <span className="flex items-center gap-2 text-sm font-semibold">
                <ShieldCheck className="w-4 h-4 text-muted-foreground" /> 개인정보처리방침
              </span>
              <ChevronDown className={cn("w-4 h-4 text-muted-foreground shrink-0 transition-transform", openLegal === "privacy" && "rotate-180")} />
            </button>
            {openLegal === "privacy" && (
              <div className="px-4 pb-4 space-y-4">
                <p className="text-xs text-muted-foreground">시행일: {PRIVACY_EFFECTIVE_DATE}</p>
                {PRIVACY_SECTIONS.map(s => (
                  <div key={s.title}>
                    <h3 className="font-bold text-xs mb-1">{s.title}</h3>
                    <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">{s.body}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
