"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Bot, Sparkles, Loader2, CheckCircle, Database, Settings2, 
  FolderKanban, MessageSquare, Microscope, Send, AlertTriangle, 
  FileText, ChevronLeft, Wand2, X, Trash2, Settings
} from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";

interface ReportSummary {
  id: string;
  question: string;
  content: string;
  degraded: boolean;
  createdBy: string;
  createdAt: string;
  sourceCount: number;
}

export default function AIAgentsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProject, setSelectedProject] = useState("");

  // Settings Modal State
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // ==========================================
  // Chatbot State & Logic
  // ==========================================
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<{ id?: string; role: string; content: string }[]>([]);
  const [chatInitializing, setChatInitializing] = useState(true);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, chatLoading]);

  useEffect(() => {
    // Load Chat History
    const loadChatHistory = async () => {
      try {
        const res = await fetch("/api/chat");
        const data = await res.json();
        if (data.success && data.messages.length > 0) {
          setChatMessages(data.messages);
        } else {
          setChatMessages([
            { 
              role: "system", 
              content: "안녕하세요! 헤이짜비 AI 비서입니다. \\n\\n프로젝트 현황이나 태스크 배정 상태에 대해 자유롭게 물어보세요! \\n\\n우측 리서치 도구를 사용하시면 사내 회의록 및 기획 문서를 종합 분석하여 깊이 있는 분석 보고서를 생성할 수 있습니다." 
            }
          ]);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setChatInitializing(false);
      }
    };
    loadChatHistory();
  }, []);

  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const userMessage = chatInput.trim();
    setChatInput("");

    setChatMessages(prev => [...prev, { role: "user", content: userMessage }]);
    setChatLoading(true);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
      });
      const data = await response.json();
      if (response.ok) {
        setChatMessages(prev => [...prev, data.reply]);
      } else {
        alert(data.error || "오류가 발생했습니다.");
      }
    } catch (error) {
      console.error(error);
    } finally {
      setChatLoading(false);
    }
  };

  // ==========================================
  // Research State & Logic
  // ==========================================
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [researchLoading, setResearchLoading] = useState(true);
  const [researchQuestion, setResearchQuestion] = useState("");
  const [researchRunning, setResearchRunning] = useState(false);
  const [researchError, setResearchError] = useState("");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  // Weekly Report Modal
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [generatedReport, setGeneratedReport] = useState("");
  const [generatingReport, setGeneratingReport] = useState(false);

  const loadReports = async () => {
    setResearchLoading(true);
    try {
      const res = await fetch('/api/research');
      const data = await res.json();
      if (Array.isArray(data)) setReports(data);
    } catch (err) {
      console.error(err);
    } finally {
      setResearchLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  const handleResearchRun = async () => {
    if (!researchQuestion.trim() || researchRunning) return;
    setResearchRunning(true);
    setResearchError("");
    try {
      const res = await fetch('/api/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: researchQuestion.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '리서치에 실패했습니다.');
      setResearchQuestion('');
      await loadReports();
      setSelectedReportId(data.id);
    } catch (err: any) {
      setResearchError(err.message || '리서치에 실패했습니다.');
    } finally {
      setResearchRunning(false);
    }
  };

  const handleDeleteReport = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('이 리서치 보고서를 삭제하시겠습니까?')) return;
    try {
      const res = await fetch("/api/research/" + id, { method: 'DELETE' });
      if (!res.ok) throw new Error('삭제에 실패했습니다.');
      if (selectedReportId === id) setSelectedReportId(null);
      await loadReports();
    } catch (err: any) {
      alert(err.message || '오류가 발생했습니다.');
    }
  };

  const selectedReport = reports.find(r => r.id === selectedReportId);

  const generateWeeklyReport = () => {
    setGeneratingReport(true);
    setIsReportModalOpen(true);

    setTimeout(() => {
      let reportMd = "# 주간 업무 및 리서치 종합 요약 리포트\\n\\n";
      reportMd += "작성일시: " + new Date().toLocaleString('ko-KR') + "\\n\\n";
      reportMd += "## 1. 최근 주요 리서치 분석 결과\\n";
      
      const recent = reports.slice(0, 3);
      if (recent.length === 0) {
        reportMd += "- 최근 진행된 리서치 내역이 없습니다.\\n";
      } else {
        recent.forEach(r => {
          reportMd += "### Q. " + r.question + "\\n> " + r.content.replace(/\\n/g, '\\n> ') + "\\n\\n";
        });
      }

      setGeneratedReport(reportMd);
      setGeneratingReport(false);
    }, 1500);
  };

  // ==========================================
  // Settings State & Logic
  // ==========================================
  const [extracting, setExtracting] = useState(false);
  const [extractSuccess, setExtractSuccess] = useState(false);
  const [extractedCount, setExtractedCount] = useState(0);

  const [agentName, setAgentName] = useState("Hey 짜비 비서");
  const [systemPrompt, setSystemPrompt] = useState("당신은 프로젝트 관리 전문가입니다. 요구사항 문서를 분석하여 명확하고 WBS 태스크(할 일)로 분해하세요.");
  const [savingConfig, setSavingConfig] = useState(false);

  const handleSaveConfig = () => {
    setSavingConfig(true);
    setTimeout(() => setSavingConfig(false), 800);
  };

  useEffect(() => {
    fetch("/api/projects")
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) {
          setProjects(data);
          if (data.length > 0) setSelectedProject(data[0].id);
        }
      });
  }, []);

  const handleExtract = async () => {
    if (!selectedProject) return;
    setExtracting(true);
    setExtractSuccess(false);
    try {
      const res = await fetch("/api/ai/extract-tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId: selectedProject }),
      });
      const data = await res.json();
      if (data.success) {
        setExtractedCount(data.tasks.length);
        setExtractSuccess(true);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setExtracting(false);
    }
  };

  return (
    <div className="w-full max-w-7xl mx-auto space-y-4 animate-in fade-in duration-500 flex-1 flex flex-col min-h-0">
      
      {/* Header */}
      <div className="flex justify-between items-center border-b border-black/5 dark:border-white/10 pb-3 shrink-0">
        <div className="flex items-center gap-3">
          <Bot className="w-7 h-7 text-primary animate-pulse" />
          <div>
            <h1 className="text-2xl font-black text-foreground tracking-tight">AI 관리 센터</h1>
          </div>
        </div>
        
        {/* Settings button */}
        <button
          onClick={() => setIsSettingsOpen(true)}
          className="flex items-center gap-1.5 px-4 py-2 bg-white border border-zinc-200 text-zinc-700 rounded-xl text-xs font-bold hover:bg-zinc-50 shadow-sm transition-all"
        >
          <Settings className="w-3.5 h-3.5" /> 에이전트 설정
        </button>
      </div>

      {/* Main Grid: Takes remaining viewport height */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 min-h-0">
        
        {/* Left Col (7/12): AI Chatbot */}
        <div className="lg:col-span-7 bg-white text-zinc-900 border border-zinc-200 rounded-3xl p-6 flex flex-col h-full shadow-2xl relative overflow-hidden">
          <div className="flex items-center justify-between mb-4 border-b border-zinc-100 pb-3 shrink-0">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-primary" />
              <span className="font-extrabold text-sm text-zinc-800">AI 어시스턴트 대화</span>
            </div>
          </div>

          {/* Chat Message History */}
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto pr-2 space-y-4 scrollbar-thin">
            {chatMessages.map((message, i) => (
              <div
                key={i}
                className={cn(
                  "flex gap-3 w-full animate-in slide-in-from-bottom-2 duration-300",
                  message.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                {message.role !== "user" && (
                  <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0 border border-primary/20">
                    <Bot className="w-4 h-4" />
                  </div>
                )}
                <div
                  className={cn(
                    "px-4 py-2.5 rounded-2xl max-w-[80%] text-sm leading-relaxed shadow-sm",
                    message.role === "user"
                      ? "bg-primary text-white rounded-br-none"
                      : "bg-zinc-50 border border-zinc-150 rounded-bl-none whitespace-pre-wrap text-zinc-800"
                  )}
                >
                  {message.content}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="flex gap-3 w-full animate-in fade-in duration-300">
                <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0 border border-primary/20 animate-spin">
                  <Bot className="w-4 h-4 text-primary" />
                </div>
                <div className="px-4 py-2.5 rounded-2xl bg-zinc-50 border border-zinc-150 rounded-bl-none text-sm text-zinc-500 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-zinc-500" />
                  답변을 작성하는 중입니다...
                </div>
              </div>
            )}
          </div>

          {/* Input Form */}
          <form onSubmit={handleChatSubmit} className="mt-4 flex gap-2 border-t border-zinc-100 pt-4 shrink-0">
            <input
              type="text"
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              placeholder="AI에게 프로젝트 관련 궁금한 점을 질문해보세요..."
              className="flex-1 px-4 py-3 bg-zinc-50 border border-transparent rounded-2xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/45 focus:bg-white transition-all text-zinc-900 placeholder:text-zinc-400"
              disabled={chatLoading}
            />
            <button
              type="submit"
              disabled={chatLoading || !chatInput.trim()}
              className="px-5 bg-primary text-white font-bold rounded-2xl text-sm flex items-center gap-1.5 hover:bg-primary/95 transition-all shadow-md shadow-primary/20 disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>

        {/* Right Col (5/12): AI Research History & Creation */}
        <div className="lg:col-span-5 bg-white text-zinc-900 border border-zinc-200 rounded-3xl p-6 flex flex-col h-full shadow-2xl relative overflow-hidden">
          <div className="flex items-center justify-between mb-4 border-b border-zinc-100 pb-3 shrink-0">
            <div className="flex items-center gap-2">
              <Microscope className="w-5 h-5 text-primary" />
              <span className="font-extrabold text-sm text-zinc-800">AI 리서치 보고서</span>
            </div>
            <button 
              onClick={generateWeeklyReport}
              className="p-1.5 bg-primary/10 text-primary border border-primary/20 rounded-xl hover:bg-primary/20 transition-all shadow-sm"
              title="주간 리포트 생성"
            >
              <Wand2 className="w-4 h-4" />
            </button>
          </div>

          {selectedReport ? (
            // Detailed report view
            <div className="flex-1 overflow-y-auto pr-1 flex flex-col scrollbar-thin">
              <div className="flex items-center justify-between mb-3">
                <button onClick={() => setSelectedReportId(null)} className="text-xs font-bold text-zinc-500 hover:text-zinc-800 flex items-center gap-1">
                  <ChevronLeft className="w-4 h-4" /> 목록으로
                </button>
                <span className="text-[10px] text-zinc-400">{new Date(selectedReport.createdAt).toLocaleDateString()}</span>
              </div>
              <h3 className="font-extrabold text-sm leading-snug mb-4 border-b border-zinc-100 pb-2 text-zinc-900">{selectedReport.question}</h3>
              <div className="prose prose-sm max-w-none text-xs text-zinc-700 leading-relaxed whitespace-pre-wrap">
                {selectedReport.content}
              </div>
            </div>
          ) : (
            // History list & Research Input Box
            <div className="flex-1 flex flex-col min-h-0">
              {/* Research Topic Input */}
              <div className="space-y-3 mb-4 border-b border-zinc-100 pb-4 shrink-0">
                <textarea
                  value={researchQuestion}
                  onChange={e => setResearchQuestion(e.target.value)}
                  placeholder="예: 최근 지연되고 있는 작업들의 원인이 무엇이고 해결책은 무엇인가요?"
                  className="w-full border border-zinc-200 bg-zinc-50 rounded-2xl p-3 text-xs h-20 resize-none focus:ring-2 focus:ring-primary/45 outline-none focus:bg-white text-zinc-900 placeholder:text-zinc-400"
                />
                {researchError && <p className="text-[10px] text-red-500 font-semibold">{researchError}</p>}
                
                <button
                  onClick={handleResearchRun}
                  disabled={researchRunning || !researchQuestion.trim()}
                  className="w-full py-2.5 bg-zinc-900 hover:bg-zinc-850 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition-colors disabled:opacity-60"
                >
                  {researchRunning ? <><Loader2 className="w-4 h-4 animate-spin" /> 리서치 진행 중...</> : <><Sparkles className="w-4 h-4" /> 심층 리서치 시작</>}
                </button>
              </div>

              {/* History List */}
              <div className="flex-1 overflow-y-auto space-y-2.5 pr-1 scrollbar-thin">
                <h4 className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2 px-1">최근 리서치 히스토리</h4>
                {researchLoading ? (
                  <div className="p-8 text-center text-zinc-500 text-sm flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> 목록 로딩 중...</div>
                ) : reports.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-zinc-400 py-10">
                    <FileText className="w-10 h-10 mb-3 opacity-20" />
                    <p className="text-xs font-semibold text-center">작성된 리서치 보고서가 없습니다.</p>
                  </div>
                ) : reports.map(r => (
                  <div
                    key={r.id}
                    onClick={() => setSelectedReportId(r.id)}
                    className="relative w-full text-left p-4 rounded-2xl bg-zinc-50/50 hover:bg-zinc-50 transition-all cursor-pointer group shadow-sm border border-zinc-150"
                  >
                    <button
                      onClick={e => handleDeleteReport(r.id, e)}
                      className="absolute top-3.5 right-3.5 p-1.5 text-zinc-400 hover:text-red-500 rounded-lg hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all"
                      title="보고서 삭제"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-bold text-zinc-500">
                      {r.degraded && <span className="bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded">근거 부족</span>}
                      <span>{r.sourceCount}개 자료 분석</span>
                    </div>
                    <p className="text-xs font-bold text-zinc-800 line-clamp-2 leading-snug">{r.question}</p>
                    <p className="text-[10px] text-zinc-400 mt-2">{new Date(r.createdAt).toLocaleDateString()}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

      </div>

      {/* 2. Settings Modal */}
      {isSettingsOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60 backdrop-blur-sm p-6 animate-in fade-in">
          <div className="bg-white text-zinc-900 border border-zinc-200 rounded-3xl shadow-2xl w-full max-w-4xl h-[550px] flex flex-col overflow-hidden animate-in zoom-in-95">
            <div className="px-6 py-4 border-b border-zinc-100 flex items-center justify-between bg-zinc-50">
              <h3 className="font-extrabold text-base flex items-center gap-2">
                <Settings2 className="w-5 h-5 text-primary" /> AI 에이전트 및 연동 설정
              </h3>
              <button 
                onClick={() => setIsSettingsOpen(false)} 
                className="p-1.5 rounded-full hover:bg-zinc-200 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 p-6 grid grid-cols-1 md:grid-cols-2 gap-6 overflow-y-auto">
              
              {/* Agent parameters */}
              <div className="space-y-4">
                <h4 className="font-bold text-sm text-zinc-800 border-b border-zinc-100 pb-2">기본 정보 설정</h4>
                <div>
                  <label className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-2 block">에이전트 이름</label>
                  <input 
                    type="text" 
                    value={agentName}
                    onChange={e => setAgentName(e.target.value)}
                    className="w-full px-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-xl text-sm transition-all outline-none font-semibold focus:bg-white focus:ring-2 focus:ring-primary/45"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-2 block">시스템 프롬프트 (가이드라인)</label>
                  <textarea 
                    value={systemPrompt}
                    onChange={e => setSystemPrompt(e.target.value)}
                    rows={6}
                    className="w-full px-4 py-3 bg-zinc-50 border border-zinc-200 rounded-xl text-sm transition-all outline-none resize-none font-medium leading-relaxed focus:bg-white focus:ring-2 focus:ring-primary/45"
                  />
                </div>
                <button 
                  onClick={handleSaveConfig}
                  disabled={savingConfig}
                  className="w-full py-3 rounded-xl bg-zinc-900 text-white font-bold hover:bg-zinc-850 transition-all flex items-center justify-center gap-2"
                >
                  {savingConfig ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                  설정 저장
                </button>
              </div>

              {/* Task Extraction */}
              <div className="space-y-4 border-l border-zinc-100 pl-6">
                <h4 className="font-bold text-sm text-zinc-800 border-b border-zinc-100 pb-2">AI WBS 업무 추출</h4>
                <p className="text-xs text-zinc-500 leading-relaxed">
                  선택된 프로젝트의 문서를 인덱싱하여 프로젝트에 알맞은 태스크(WBS) 목록을 자동 분해하고 칸반 보드에 즉시 이식합니다.
                </p>
                <div>
                  <label className="text-xs font-bold text-primary uppercase tracking-wider mb-2 block">대상 프로젝트</label>
                  <div className="relative">
                    <Database className="w-4 h-4 text-primary absolute left-4 top-1/2 -translate-y-1/2" />
                    <select 
                      value={selectedProject}
                      onChange={e => setSelectedProject(e.target.value)}
                      className="w-full pl-11 pr-4 py-3 bg-zinc-50 border border-zinc-200 rounded-xl text-sm transition-all outline-none font-bold cursor-pointer"
                    >
                      {projects.map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {extractSuccess && (
                  <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 p-4 rounded-xl flex flex-col gap-2">
                    <div className="flex items-center gap-2 font-bold text-xs">
                      <CheckCircle className="w-4 h-4" /> 성공적으로 완료되었습니다!
                    </div>
                    <p className="text-[10px]">새로운 <strong>{extractedCount}개</strong>의 태스크 카드를 이식했습니다.</p>
                    <Link 
                      href={"/projects/" + selectedProject}
                      onClick={() => setIsSettingsOpen(false)}
                      className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-emerald-500 text-white rounded-lg text-xs font-bold hover:bg-emerald-600 transition-all self-start"
                    >
                      <FolderKanban className="w-3.5 h-3.5" /> 칸반보드 보기
                    </Link>
                  </div>
                )}
                
                <button 
                  onClick={handleExtract}
                  disabled={extracting || !selectedProject}
                  className="w-full py-4 rounded-xl bg-primary text-white font-bold hover:bg-primary/95 transition-all flex items-center justify-center gap-2 shadow-lg shadow-primary/20 disabled:opacity-50"
                >
                  {extracting ? <><Loader2 className="w-5 h-5 animate-spin" /> 분석 중...</> : <><Sparkles className="w-5 h-5" /> 자동 업무 추출 시작</>}
                </button>
              </div>

            </div>
          </div>
        </div>
      )}

      {/* Weekly Report Modal */}
      {isReportModalOpen && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 backdrop-blur-sm p-6 animate-in fade-in">
          <div className="bg-white text-zinc-900 border border-zinc-200 rounded-3xl shadow-2xl w-full max-w-3xl h-full max-h-[700px] flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-zinc-150 flex items-center justify-between bg-zinc-50">
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Wand2 className="w-5 h-5 text-primary" /> 주간 성과 및 리서치 요약 리포트
              </h3>
              <button onClick={() => setIsReportModalOpen(false)} className="p-1.5 rounded-full hover:bg-zinc-200 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 p-6 overflow-y-auto">
              {generatingReport ? (
                <div className="flex flex-col items-center justify-center h-full space-y-4">
                  <Loader2 className="w-8 h-8 animate-spin text-primary" />
                  <p className="font-bold text-sm">리서치 데이터를 가공하여 종합 리포트를 만들고 있습니다...</p>
                </div>
              ) : (
                <div className="prose prose-sm max-w-none text-sm text-zinc-700 leading-relaxed whitespace-pre-wrap">
                  {generatedReport}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
