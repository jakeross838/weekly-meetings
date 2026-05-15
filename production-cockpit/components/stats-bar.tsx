interface StatsBarProps {
  open: number;
  doneThisWeek: number;
  overdue: number;
}

export function StatsBar({ open, doneThisWeek, overdue }: StatsBarProps) {
  return (
    <div className="grid grid-cols-3 border-b border-rule bg-paper">
      <Stat label="Open" value={open} />
      <Stat label="Done this week" value={doneThisWeek} divider />
      <Stat
        label="Overdue"
        value={overdue}
        divider
        accent={overdue > 0 ? "urgent" : undefined}
      />
    </div>
  );
}

function Stat({
  label,
  value,
  divider,
  accent,
}: {
  label: string;
  value: number;
  divider?: boolean;
  accent?: "urgent";
}) {
  return (
    <div
      className={
        "px-4 py-6 flex flex-col items-center text-center " +
        (divider ? "border-l border-rule" : "")
      }
    >
      <span
        className={
          "font-mono text-5xl font-medium leading-none tabular-nums " +
          (accent === "urgent" ? "text-urgent" : "text-ink")
        }
      >
        {value}
      </span>
      <span className="mt-2 font-mono text-[11px] tracking-[0.18em] uppercase text-ink-3">
        {label}
      </span>
    </div>
  );
}
