"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Settings as SettingsIcon, Loader2, Save, CheckCircle2, Sparkles, FolderKanban, HelpCircle, Mail, ChevronDown, FileText, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentBadge } from "@/components/ui/AgentBadge";
import { parseAgentConfig, DEFAULT_AGENT_CONFIG, type AgentConfig } from "@/lib/agentConfig";
import { TERMS_ARTICLES, TERMS_EFFECTIVE_DATE, PRIVACY_SECTIONS, PRIVACY_EFFECTIVE_DATE } from "@/lib/legalContent";

const SUPPORT_EMAIL = "kimjae9360@gmail.com";

// 사용방법 위주 FAQ — 실제 파이프라인/화면 동작을 근거로 작성(일반적인 문구 아님)
const FAQ_ITEMS = [
  { q: "문서는 어떻게 만드나요?", a: "문서생성 페이지에서 \"새 회의록/문서\"로 회의록을 등록하면, AI가 기획서를 생성합니다. PM 검토·승인을 거치면 요구사항정의서 생성 → 승인 → 업무 자동 추출까지 이어집니다." },
  { q: "업무 담당자는 어떻게 배정하나요?", a: "요구사항정의서가 승인되면 문서생성의 \"업무 배분\" 탭에서 AI 추천을 받아 배정하거나, 업무관리 칸반에서 직접 담당자를 지정해 배분 승인을 요청할 수 있습니다." },
  { q: "\"배분승인대기\"는 무슨 뜻인가요?", a: "업무 완료 승인이 아니라, 담당자 지정에 대한 PM 승인 대기 상태입니다. PM이 승인해야 그 업무가 \"진행 중\"으로 넘어갑니다." },
  { q: "알림은 어디서 확인하나요?", a: "모든 화면 상단 우측 종 아이콘에서 확인할 수 있습니다. 안읽음이 있으면 아이콘이 주황색으로 바뀌고, 항목을 클릭하면 관련 화면으로 이동하며 읽음 처리됩니다." },
  { q: "설정의 \"에이전트 설정\"은 무엇을 바꾸나요?", a: "AI가 문서/업무를 생성할 때의 일관성(temperature)과, 업무 배분 시 한 번에 추출할 업무 개수 범위를 조정합니다. 환각 방지를 위해 일관성은 일정 범위 안에서만 조정할 수 있습니다." },
  { q: "PM과 일반유저는 권한이 어떻게 다른가요?", a: "PM은 프로젝트 생성, 문서·업무 배분 승인, 직원관리, 에이전트 설정 등을 할 수 있습니다. 일반유저는 본인이 담당한 업무 위주로 진행 상황을 관리합니다." },
  { q: "비밀번호를 잊어버렸어요.", a: "현재는 자가 비밀번호 재설정 기능이 없습니다. 소속 PM(관리자)에게 계정 초기화를 요청해 주세요." },
];

type Project = {
  id: string;
  agentConfig: string | null;
};

export default function SettingsPage() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [agentConfig, setAgentConfig] = useState<AgentConfig>(DEFAULT_AGENT_CONFIG);
  const [savingAgents, setSavingAgents] = useState(false);
  const [savedAgents, setSavedAgents] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  // 에이전트 설정은 PM 전용(일반유저에게는 섹션 자체를 안 보여줌)이라 collapse 상태는 PM한테만 의미가 있다.
  // 기본값은 접힌 상태 — 페이지 진입 시 바로 눈에 띄지 않아도 되는 설정이라는 판단(사용자 요청).
  const [agentSectionOpen, setAgentSectionOpen] = useState(false);
  const [openLegal, setOpenLegal] = useState<"terms" | "privacy" | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        // 예전엔 목록 조회 → 첫 프로젝트 id로 상세 조회 2단계였다 — 원격 DB 왕복이 하나 늘 때마다
        // 체감 지연이 커서(/api/projects/current 참고) 단일 요청으로 합쳤다.
        const res = await fetch("/api/projects/current");
        const detail = await res.json();
        if (detail.success && detail.data) {
          const p: Project = detail.data;
          setProject(p);
          setAgentConfig(parseAgentConfig(p.agentConfig));
        }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const saveAgents = async () => {
    if (!project) return;
    setSavingAgents(true); setSavedAgents(false);
    try {
      const res = await fetch(`/api/projects/${project.id}/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agentConfig }),
      });
      const data = await res.json();
      // 서버가 clamp한 최종값으로 화면을 맞춘다 — 슬라이더로는 이미 범위 안이라 보통 그대로지만,
      // min/max 업무 개수처럼 두 값이 서로 얽힌 필드는 서버 쪽 보정이 있을 수 있다.
      if (res.ok && data.data?.agentConfig) setAgentConfig(parseAgentConfig(data.data.agentConfig));
      if (res.ok) { setSavedAgents(true); setTimeout(() => setSavedAgents(false), 2000); }
    } finally {
      setSavingAgents(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-[60vh]"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-3">
        <FolderKanban className="w-10 h-10 text-muted-foreground/30" />
        <p className="text-muted-foreground">
          {isPM ? "아직 프로젝트가 없습니다. 먼저 프로젝트를 생성해주세요." : "아직 프로젝트가 없습니다. PM에게 프로젝트 생성을 요청해주세요."}
        </p>
        {isPM && (
          <Link href="/project/new" className="inline-block mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold hover:bg-primary/90 transition-colors">
            첫 프로젝트 만들기
          </Link>
        )}
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto space-y-6 animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 text-muted-foreground mb-1">
          <SettingsIcon className="w-5 h-5 text-primary" />
          <h1 className="text-3xl font-black text-foreground tracking-tight">설정</h1>
        </div>
        <p className="text-muted-foreground">
          {isPM ? "AI 에이전트 설정, 자주 묻는 질문, 법적 고지를 확인합니다." : "자주 묻는 질문과 법적 고지를 확인합니다."}
        </p>
      </div>

      {/* 에이전트 설정 — 일반유저는 조정할 일이 없어 섹션 자체를 안 보여준다(PM 전용) */}
      {isPM && (
        <section className="glass rounded-2xl border border-border overflow-hidden">
          <button
            onClick={() => setAgentSectionOpen(v => !v)}
            className="w-full flex items-center justify-between gap-3 p-6 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
          >
            <h2 className="text-lg font-bold flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" /> 에이전트 설정
            </h2>
            <ChevronDown className={cn("w-5 h-5 text-muted-foreground shrink-0 transition-transform", agentSectionOpen && "rotate-180")} />
          </button>

          {agentSectionOpen && (
            <div className="px-6 pb-6 space-y-5">
              <p className="text-xs text-muted-foreground -mt-2">
                문서생성 파이프라인의 AI 에이전트 3종을 세부 조정합니다. 값은 실제 생성 API 호출에 그대로 반영됩니다.
                &ldquo;원본에 없는 내용은 지어내지 않는다&rdquo;는 환각 방지 원칙을 지키기 위해 다양성(temperature)은
                0~0.3 범위로만 조정할 수 있습니다.
              </p>

              <AgentTemperatureCard
                agent="proposal"
                title="기획서 생성 에이전트"
                description="회의록/메모를 바탕으로 프로젝트 기획서 초안을 작성합니다."
                temperature={agentConfig.proposal.temperature}
                onChange={t => setAgentConfig(c => ({ ...c, proposal: { temperature: t } }))}
                editable={isPM}
              />
              <AgentTemperatureCard
                agent="reqSpec"
                title="요구사항정의서 생성 에이전트"
                description="승인된 기획서를 바탕으로 개발 가능한 수준의 요구사항정의서를 작성합니다."
                temperature={agentConfig.reqSpec.temperature}
                onChange={t => setAgentConfig(c => ({ ...c, reqSpec: { temperature: t } }))}
                editable={isPM}
              />
              <AgentTemperatureCard
                agent="taskAssign"
                title="업무 배분 에이전트"
                description="승인된 요구사항정의서를 실행 가능한 업무 단위로 쪼갭니다."
                temperature={agentConfig.taskAssign.temperature}
                onChange={t => setAgentConfig(c => ({ ...c, taskAssign: { ...c.taskAssign, temperature: t } }))}
                editable={isPM}
              >
                <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border">
                  <label className="text-xs font-semibold text-muted-foreground shrink-0">한 번에 추출할 업무 개수</label>
                  <input
                    type="number" min={1} max={agentConfig.taskAssign.maxTasks} step={1}
                    value={agentConfig.taskAssign.minTasks}
                    onChange={e => setAgentConfig(c => ({ ...c, taskAssign: { ...c.taskAssign, minTasks: Math.max(1, Number(e.target.value) || 1) } }))}
                    className="w-16 px-2 py-1 bg-black/5 dark:bg-white/5 border border-border rounded-lg text-xs text-center focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60"
                  />
                  <span className="text-xs text-muted-foreground">~</span>
                  <input
                    type="number" min={agentConfig.taskAssign.minTasks} max={15} step={1}
                    value={agentConfig.taskAssign.maxTasks}
                    onChange={e => setAgentConfig(c => ({ ...c, taskAssign: { ...c.taskAssign, maxTasks: Math.min(15, Number(e.target.value) || c.taskAssign.minTasks) } }))}
                    className="w-16 px-2 py-1 bg-black/5 dark:bg-white/5 border border-border rounded-lg text-xs text-center focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60"
                  />
                  <span className="text-xs text-muted-foreground">개 (기본 3~7)</span>
                </div>
              </AgentTemperatureCard>

              <button onClick={saveAgents} disabled={savingAgents} className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50">
                {savingAgents ? <Loader2 className="w-4 h-4 animate-spin" /> : savedAgents ? <CheckCircle2 className="w-4 h-4" /> : <Save className="w-4 h-4" />}
                {savedAgents ? "저장됨" : "저장하기"}
              </button>
            </div>
          )}
        </section>
      )}

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

function AgentTemperatureCard({
  agent, title, description, temperature, onChange, editable, children,
}: {
  agent: "proposal" | "reqSpec" | "taskAssign";
  title: string;
  description: string;
  temperature: number;
  onChange: (t: number) => void;
  editable: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border p-4">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-semibold text-sm flex items-center gap-2">{title} <AgentBadge agent={agent} /></h3>
        <span className="text-xs font-mono text-muted-foreground">{temperature.toFixed(2)}</span>
      </div>
      <p className="text-xs text-muted-foreground mb-3">{description}</p>
      <input
        type="range" min={0} max={0.3} step={0.05}
        value={temperature}
        onChange={e => onChange(Number(e.target.value))}
        disabled={!editable}
        className="w-full accent-primary disabled:opacity-60"
      />
      <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
        <span>0 · 항상 같은 결과(결정적)</span>
        <span>0.3 · 표현에 약간의 다양성</span>
      </div>
      {children}
    </div>
  );
}
