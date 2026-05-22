/**
 * Ross Built logo — the official brand assets (copied into /public from the
 * Ross Built brand kit): a stone-blue circular logomark + the "ROSS BUILT"
 * wordmark. We render the real SVGs rather than a hand-drafted stand-in.
 *
 * Plain <img> (not next/image) so the SVG is served straight from /public with
 * its baked-in brand colors — no optimizer, no dangerouslyAllowSVG config.
 */

/** The circular logomark on its own (stone blue), e.g. favicons / loading. */
export function RossBuiltMark({
  size = 28,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/ross-built-mark.svg"
      alt=""
      aria-hidden
      width={size}
      height={size}
      style={{ width: size, height: size }}
      className={className}
    />
  );
}

/** Text-only wordmark fallback (kept for non-image contexts). */
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

/**
 * Logo lockup for header use — the official horizontal logo (mark + wordmark).
 * `size` is the rendered height in px; width scales to keep the brand ratio.
 */
export function RossBuiltLogo({
  className = "",
  size = 24,
}: {
  className?: string;
  size?: number;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/ross-built-logo.svg"
      alt="Ross Built"
      height={size}
      style={{ height: size, width: "auto" }}
      className={"select-none " + className}
    />
  );
}
