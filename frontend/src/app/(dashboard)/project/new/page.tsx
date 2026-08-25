"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FolderPlus, Loader2 } from "lucide-react";

// 예전엔 이 화면이 "AI 기획 자동화 마법사"로, 회의록 하나로 기획서/요구사항정의서/업무까지
// 한 번에 만들어버렸다. 하지만 그 흐름이 실제 문서생성 파이프라인(/documents)과 완전히
// 어긋나 있었다 — 호출하는 AI API가 기획서/요구사항정의서를 구분해서 만들지 않았고,
// PM 검토/승인 게이트도 전부 건너뛰었으며, "음성 녹음"/"파일 업로드"는 실제로 동작하지
// 않는 가짜 텍스트였다. 그래서 마법사는 없애고, 여기서는 프로젝트 껍데기(이름/설명)만
// 최소한으로 만든 뒤 실제 파이프라인이 있는 /documents로 보낸다 — 회의록 등록부터
// AI 기획서 생성까지는 전부 그 화면의 정식 흐름을 그대로 타게 된다.
export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const handleCreate = async () => {
    if (!name.trim()) {
      setError("프로젝트 이름을 입력해주세요.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), description: description.trim() || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "프로젝트 생성에 실패했습니다.");
      router.push("/documents");
    } catch (e: any) {
      setError(e.message || "프로젝트 생성 중 오류가 발생했습니다.");
      setCreating(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto py-16 px-4">
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-primary/10 mb-4 border border-primary/20">
          <FolderPlus className="w-7 h-7 text-primary" />
        </div>
        <h1 className="text-2xl font-extrabold mb-2">새 프로젝트 만들기</h1>
        <p className="text-muted-foreground text-sm">
          프로젝트를 만들고 나면 문서생성 화면에서 회의록을 등록해 AI 기획서 생성부터 시작할 수 있어요.
        </p>
      </div>

      <div className="glass rounded-2xl border border-border p-6 space-y-4">
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-sm">{error}</div>
        )}
        <div>
          <label className="text-sm font-semibold mb-1.5 block">프로젝트 이름 *</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="예: 사내 인트라넷 모바일 앱 개발"
            className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
        <div>
          <label className="text-sm font-semibold mb-1.5 block">설명 (선택)</label>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            placeholder="이 프로젝트가 무엇을 위한 것인지 한두 줄로 적어주세요."
            className="w-full px-4 py-2.5 bg-black/5 dark:bg-white/5 border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
          />
        </div>
        <button
          onClick={handleCreate}
          disabled={creating || !name.trim()}
          className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-primary-foreground text-sm font-bold hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderPlus className="w-4 h-4" />}
          프로젝트 생성하고 문서생성으로 이동
        </button>
      </div>
    </div>
  );
}
