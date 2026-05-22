"use client";

// Mobile ⇄ Desktop view toggle. The app is mobile-first (every page caps at
// max-w-[560px]); flipping to desktop adds a `view-desktop` class on <html>,
// which a single rule in globals.css widens to a desktop column. Persisted in
// localStorage; applied pre-render by the inline script in app/layout.tsx so
// there's no flash. Hidden on phones (where widening is a no-op anyway).

import { useEffect, useState } from "react";

export function ViewToggle() {
  const [desktop, setDesktop] = useState(false);

  useEffect(() => {
    setDesktop(document.documentElement.classList.contains("view-desktop"));
  }, []);

  function toggle() {
    const next = !desktop;
    setDesktop(next);
    document.documentElement.classList.toggle("view-desktop", next);
    try {
      localStorage.setItem("viewMode", next ? "desktop" : "mobile");
    } catch {
      /* private mode / storage disabled — toggle still works for this page */
    }
  }

  return (
    <button
      onClick={toggle}
      className="hidden sm:inline-block hover:text-ink transition-colors"
      title={
        desktop
          ? "Switch to mobile (narrow) view"
          : "Switch to desktop (wide) view"
      }
      aria-label="Toggle desktop or mobile view"
    >
      {desktop ? "Mobile view" : "Desktop view"}
    </button>
  );
}
