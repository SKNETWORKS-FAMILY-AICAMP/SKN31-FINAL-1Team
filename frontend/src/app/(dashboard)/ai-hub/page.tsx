"use client";

import { useState, useRef, useEffect } from "react";
import { Sparkles, Bot, Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export default function AIHubPage() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<{ id?: string, role: string; content: string }[]>([]);
  const [isInitializing, setIsInitializing] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  useEffect(() => {
    // Load chat history
    const loadMessages = async () => {
      try {
        const res = await fetch("/api/chat");
        const data = await res.json();
        if (data.success && data.messages.length > 0) {
          setMessages(data.messages);
        } else {
          // Default welcome message if empty
          setMessages([
            { 
              role: "system", 
              content: "안녕하세요! 헤이짜비 사내 데이터 전용 AI 어시스턴트입니다.\n\n프로젝트 현황, 칸반 보드 진행 상황, 팀원 정보에 대해 질문해보세요.\n\n어떤 도움이 필요하신가요?" 
            }
          ]);
        }
      } catch (e) {
        console.error("Failed to load messages", e);
      } finally {
        setIsInitializing(false);
      }
    };
    loadMessages();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    // Optimistic UI update
    setMessages(prev => [...prev, { role: "user", content: userMessage }]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
      });

      const data = await response.json();
      if (response.ok) {
        setMessages(prev => [...prev, data.reply]);
      } else {
        alert(data.error || "오류가 발생했습니다.");
      }
    } catch (error) {
      console.error(error);
      alert("네트워크 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  if (isInitializing) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-80px)] max-w-5xl mx-auto w-full p-4 relative">
      <div className="flex items-center gap-3 mb-6 bg-background/50 backdrop-blur-md p-4 rounded-2xl border border-border shadow-sm">
        <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20">
          <Sparkles className="w-6 h-6 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI Hub</h1>
          <p className="text-muted-foreground text-sm mt-1">프로젝트 데이터 기반 사내 업무 어시스턴트</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto mb-6 pr-4 space-y-6 scrollbar-thin">
        {messages.map((message, i) => (
          <div
            key={message.id || i}
            className={cn(
              "flex gap-4 w-full animate-in slide-in-from-bottom-2 duration-300",
              message.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            {message.role !== "user" && (
              <div className={cn(
                "w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm",
                message.role === "system" ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground"
              )}>
                <Bot className="w-5 h-5" />
              </div>
            )}
            
            <div
              className={cn(
                "px-5 py-3.5 rounded-2xl max-w-[80%] text-sm leading-relaxed shadow-sm",
                message.role === "user"
                  ? "bg-primary text-primary-foreground rounded-br-none"
                  : message.role === "system"
                  ? "bg-muted text-foreground border border-border rounded-bl-none whitespace-pre-wrap"
                  : "glass text-foreground border border-border rounded-bl-none whitespace-pre-wrap"
              )}
            >
              {message.content}
            </div>
            
            {message.role === "user" && (
              <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center shrink-0 shadow-sm">
                <span className="text-xs font-semibold">ME</span>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-4 w-full animate-in fade-in duration-300">
            <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center shrink-0 shadow-sm">
              <Bot className="w-5 h-5 text-primary" />
            </div>
            <div className="px-5 py-4 rounded-2xl bg-muted border border-border rounded-bl-none flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground font-medium">데이터를 분석하고 있습니다...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="sticky bottom-0 pb-4 pt-2 bg-background">
        <form onSubmit={handleSubmit} className="relative group">
          <div className="absolute -inset-1 bg-gradient-to-r from-primary/30 to-blue-500/30 rounded-2xl blur opacity-25 group-focus-within:opacity-100 transition duration-500" />
          <div className="relative flex bg-black/5 dark:bg-white/5 border border-border rounded-2xl shadow-lg focus-within:ring-2 focus-within:ring-primary/50 transition-all overflow-hidden">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="무엇이든 물어보세요..."
              className="flex-1 bg-transparent border-none px-6 py-4 outline-none text-sm"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-6 flex items-center justify-center text-primary hover:bg-primary hover:text-primary-foreground disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-primary transition-colors font-medium border-l border-border"
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <>
                  <span className="mr-2 hidden sm:inline">전송</span>
                  <Send className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
