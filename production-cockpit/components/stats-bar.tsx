interface StatsBarProps {
  open: number;
  doneThisWeek: number;
  overdue: number;
}

export function StatsBar({ open, doneThisWeek, overdue }: StatsBarProps) {
  return (
    <div className="grid grid-cols-3 border-b border-rule rise" style={{ animationDelay: "60ms" }}>
      <Stat label="Open" value={open} />
      <Stat label="Done · wk" value={doneThisWeek} divider />
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
  const display = String(value).padStart(3, "0");
  return (
    <div
      className={
        "px-4 py-5 flex flex-col items-start " +
        (divider ? "border-l border-rule" : "")
      }
    >
      <span
        className={
          "font-mono text-4xl font-medium leading-none tabular-nums " +
          (accent === "urgent" ? "text-urgent" : "")
        }
      >
        {display}
      </span>
      <span className="mt-2 font-mono text-[10px] tracking-[0.22em] uppercase text-muted-foreground">
        {label}
      </span>
    </div>
  );
}
