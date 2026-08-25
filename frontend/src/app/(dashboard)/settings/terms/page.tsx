"use client";

import Link from "next/link";
import { ArrowLeft, FileText } from "lucide-react";
import { TERMS_ARTICLES, TERMS_EFFECTIVE_DATE } from "@/lib/legalContent";

export default function TermsPage() {
  return (
    <div className="w-full max-w-3xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col gap-2">
        <Link href="/settings" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit">
          <ArrowLeft className="w-4 h-4" /> 설정으로 돌아가기
        </Link>
        <div className="flex items-center gap-3 text-muted-foreground mt-2">
          <FileText className="w-5 h-5 text-primary" />
          <h1 className="text-3xl font-black text-foreground tracking-tight">이용약관</h1>
        </div>
        <p className="text-xs text-muted-foreground">시행일: {TERMS_EFFECTIVE_DATE}</p>
      </div>

      <div className="glass rounded-2xl border border-border p-6 md:p-8 space-y-6">
        {TERMS_ARTICLES.map((a) => (
          <div key={a.title}>
            <h2 className="font-bold text-sm mb-2">{a.title}</h2>
            <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{a.body}</p>
          </div>
        ))}
        <div className="pt-4 border-t border-border">
          <p className="text-sm text-muted-foreground">부칙: 이 약관은 {TERMS_EFFECTIVE_DATE}부터 시행합니다.</p>
        </div>
      </div>
    </div>
  );
}
