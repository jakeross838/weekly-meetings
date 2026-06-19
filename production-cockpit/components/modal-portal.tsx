"use client";

// Renders its children into <body> via a React portal, so a full-screen
// overlay (`fixed inset-0`) always resolves against the viewport — never
// against a transformed/filtered ancestor (e.g. <main>'s entrance animation),
// which would otherwise trap `position: fixed` and push the modal off-screen.
//
// Also locks background scroll while mounted, so the page behind the overlay
// can't scroll out from under it. Mount this only when the modal is open
// (every caller already early-returns null when closed), so the lock engages
// on open and releases on close.

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export function ModalPortal({ children }: { children: ReactNode }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Lock background scroll. Compensate for the vanished scrollbar so the
    // page doesn't shift sideways on desktop.
    const { body, documentElement: html } = document;
    const scrollbar = window.innerWidth - html.clientWidth;
    const prevOverflow = body.style.overflow;
    const prevPad = body.style.paddingRight;
    body.style.overflow = "hidden";
    if (scrollbar > 0) body.style.paddingRight = `${scrollbar}px`;
    return () => {
      body.style.overflow = prevOverflow;
      body.style.paddingRight = prevPad;
    };
  }, []);

  if (!mounted) return null;
  return createPortal(children, document.body);
}
