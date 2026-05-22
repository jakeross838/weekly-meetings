// Shared loading skeleton shown during route navigation (Next.js loading.tsx).
// Keeps the header in place and shimmers the content area so moving between
// pages feels instant instead of blank/stale.

import { Header } from "@/components/header";

export function PageSkeleton() {
  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background">
      <Header />
      <div className="px-5 pt-8">
        <div className="skeleton h-7 w-44" />
        <div className="skeleton mt-3 h-4 w-28" />
        <div className="mt-8 space-y-2.5">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="skeleton h-12 w-full" />
          ))}
        </div>
      </div>
    </main>
  );
}
