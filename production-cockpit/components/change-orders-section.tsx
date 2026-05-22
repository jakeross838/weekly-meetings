// Change-orders section for the job page (under the pay app). Shows the approved
// total + count always; the list (editable status/price, deletable) is in a
// collapsed details. Edits/deletes go through the manual-wins CO routes.

import { EditableText } from "@/components/editable-text";
import { DeleteButton } from "@/components/delete-button";

export interface ChangeOrderRow {
  id: string;
  co_number: string | null;
  title: string | null;
  status: string | null;
  owner_price: number | null;
  date_approved: string | null;
}

function usd(n: number | null): string {
  return "$" + Math.round(Number(n) || 0).toLocaleString("en-US");
}
function coTone(status: string | null): string {
  const s = (status || "").toLowerCase();
  if (s.includes("approv")) return "text-success";
  if (s.includes("declin") || s.includes("void") || s.includes("reject")) return "text-urgent";
  return "text-gold"; // draft / pending / submitted
}
const isApproved = (s: string | null) => (s || "").toLowerCase().includes("approv");

export function ChangeOrdersSection({ cos }: { cos: ChangeOrderRow[] }) {
  if (cos.length === 0) return null;
  const total = cos.reduce((s, c) => s + (Number(c.owner_price) || 0), 0);
  const approved = cos.filter((c) => isApproved(c.status));
  const approvedTotal = approved.reduce((s, c) => s + (Number(c.owner_price) || 0), 0);
  return (
    <section className="px-5 pt-2">
      <div className="border border-rule p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Change orders · {cos.length}
          </h2>
          <span className="font-mono text-sm tabular-nums text-foreground">
            {usd(approvedTotal)} <span className="text-ink-3 text-xs">approved</span>
          </span>
        </div>
        <p className="mt-1 font-mono text-[10px] tracking-[0.14em] uppercase text-ink-3">
          {approved.length} approved · {usd(total)} total submitted
        </p>

        <details className="mt-3 border-t border-rule pt-2">
          <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 py-1">
            All change orders · {cos.length}
          </summary>
          <ul className="mt-2 space-y-2">
            {cos.map((c) => (
              <li
                key={c.id}
                className="flex items-baseline justify-between gap-2 border-t border-rule-soft pt-2 text-xs first:border-t-0"
              >
                <span className="min-w-0 flex-1">
                  <span className="font-mono text-[11px] text-ink-3">
                    {c.co_number ?? "CO"}
                  </span>{" "}
                  <EditableText
                    value={c.title}
                    display={c.title || "—"}
                    field="title"
                    endpoint={`/v2/api/change-orders/${c.id}/edit`}
                    placeholder="title"
                    className="text-foreground"
                  />
                  <span className="block">
                    <EditableText
                      value={c.status}
                      display={c.status || "—"}
                      field="status"
                      endpoint={`/v2/api/change-orders/${c.id}/edit`}
                      placeholder="status"
                      className={coTone(c.status)}
                    />
                    {c.date_approved && (
                      <span className="text-ink-3"> · {c.date_approved}</span>
                    )}
                  </span>
                </span>
                <EditableText
                  value={c.owner_price}
                  type="money"
                  display={usd(c.owner_price)}
                  field="owner_price"
                  endpoint={`/v2/api/change-orders/${c.id}/edit`}
                  className="shrink-0 font-mono tabular-nums text-foreground"
                  inputClassName="bg-paper border border-ink px-1 py-0.5 text-xs text-ink focus:outline-none w-24 text-right"
                />
                <DeleteButton
                  endpoint={`/v2/api/change-orders/${c.id}/delete`}
                  label={`CO ${c.co_number ?? ""}`.trim()}
                  confirmLabel="Delete?"
                />
              </li>
            ))}
          </ul>
        </details>
      </div>
    </section>
  );
}
