"use client";

import { useState } from "react";
import OverviewView from "@/components/dashboard/OverviewView";
import AnalyticsView from "@/components/dashboard/AnalyticsView";
import { cn } from "@/lib/utils";
import { LayoutDashboard, TrendingUp } from "lucide-react";
import { useAuth } from "@/lib/auth";

export default function DashboardContainer() {
  const { user } = useAuth();
  const isPM = user?.role === "PM";
  const [activeTab, setActiveTab] = useState<"overview" | "analytics">("overview");

  return (
    <div className="space-y-6">
      {/* Tabs — 성과 통계(팀 전체 KPI)는 PM 전용 */}
      {isPM ? (
        <div className="flex border-b border-foreground/10 mb-6 w-max">
          <button
            onClick={() => setActiveTab("overview")}
            className={cn(
              "flex items-center gap-2 px-6 py-3 font-bold transition-colors border-b-2",
              activeTab === "overview" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5"
            )}
          >
            <LayoutDashboard className="w-5 h-5" /> 개요
          </button>
          <button
            onClick={() => setActiveTab("analytics")}
            className={cn(
              "flex items-center gap-2 px-6 py-3 font-bold transition-colors border-b-2",
              activeTab === "analytics" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5"
            )}
          >
            <TrendingUp className="w-5 h-5" /> 성과 통계
          </button>
        </div>
      ) : null}

      <div className="mt-4">
        {activeTab === "overview" || !isPM ? <OverviewView /> : <AnalyticsView />}
      </div>
    </div>
  );
}