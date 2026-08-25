"use client";

import { MobileNav } from "@/components/layout/MobileNav";
import { SidebarProvider } from "@/components/layout/SidebarContext";
import { DashboardContent } from "@/components/layout/DashboardContent";
import { useAuth } from "@/lib/auth";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
    } else if (user?.isFirstLogin) {
      router.push("/onboarding");
    }
  }, [user, isLoading, router]);

  if (isLoading || !user || user.isFirstLogin) {
    return <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">로딩 중...</div>;
  }

  return (
    <SidebarProvider>
      <div className="min-h-screen bg-background">
        <DashboardContent>
          {children}
        </DashboardContent>
        <MobileNav />
      </div>
    </SidebarProvider>
  );
}
