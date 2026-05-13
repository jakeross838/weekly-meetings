/**
 * Ross Built mark — a hand-drafted roofline pictogram (peak above a
 * baseline) paired with the wordmark. Uses currentColor so it inherits
 * whichever ink color it's dropped into.
 */
export function RossBuiltMark({
  size = 28,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 36 36"
      width={size}
      height={size}
      aria-hidden
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="square"
      strokeLinejoin="miter"
    >
      {/* Roof peak */}
      <path d="M5 20 L18 7 L31 20" />
      {/* Right slope inner — gives the mark depth, like a section cut */}
      <path d="M18 7 L18 20" opacity="0.4" />
      {/* Ground line */}
      <line x1="3" y1="29" x2="33" y2="29" />
      {/* Center tick on ground */}
      <line x1="18" y1="29" x2="18" y2="32" />
    </svg>
  );
}

export function RossBuiltWordmark({
  className = "",
}: {
  className?: string;
}) {
  return (
    <span
      className={
        "font-head font-semibold uppercase tracking-[0.18em] leading-none " +
        className
      }
    >
      Ross Built
    </span>
  );
}

/** Logo lockup: mark + wordmark side-by-side, sized for header use. */
export function RossBuiltLogo({
  className = "",
  size = 24,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <div className={"inline-flex items-center gap-2.5 text-ink " + className}>
      <RossBuiltMark size={size} />
      <RossBuiltWordmark className="text-[12px]" />
    </div>
  );
}
