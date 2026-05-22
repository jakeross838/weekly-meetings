// Job page has its own header (not the global one), so its loading state uses a
// matching "← Jobs" placeholder + content shimmer rather than PageSkeleton.

export default function Loading() {
  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background px-5 py-16">
      <div className="skeleton h-3 w-16" />
      <div className="skeleton mt-4 h-8 w-56" />
      <div className="skeleton mt-2 h-4 w-40" />
      <div className="mt-8 space-y-3">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="skeleton h-16 w-full" />
        ))}
      </div>
    </main>
  );
}
