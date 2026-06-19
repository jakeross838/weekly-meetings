"use client";

// Wraps the transcript ImportForm in a pop-up modal so /import isn't dominated
// by the (large, 2-step) form. A button opens it; the form's own steps + the
// duplicate-upload warning live inside.

import { useState, type ComponentProps } from "react";
import { ImportForm } from "@/components/import-form";
import { ModalPortal } from "@/components/modal-portal";

export function TranscriptImportModal(props: ComponentProps<typeof ImportForm>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="bg-ink text-paper px-4 py-2.5 text-sm font-medium hover:bg-accent transition-colors"
      >
        ✦ Import transcript
      </button>

      {open && (
        <ModalPortal>
        <div
          className="fixed inset-0 z-50 bg-ink/50 flex items-start justify-center overflow-y-auto px-3 py-6"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="my-4 w-full max-w-3xl border border-rule bg-background shadow-xl">
            <header className="sticky top-0 z-10 flex items-center justify-between border-b border-rule bg-background px-5 pt-4 pb-3">
              <h2 className="font-head text-lg font-semibold text-foreground">
                Import transcript
              </h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-xs tracking-[0.18em] uppercase text-ink-3 hover:text-ink"
              >
                ✕ Close
              </button>
            </header>
            <div className="px-5 py-4">
              <ImportForm {...props} />
            </div>
          </div>
        </div>
        </ModalPortal>
      )}
    </>
  );
}
