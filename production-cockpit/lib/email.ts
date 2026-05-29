// Email sender via Resend. If RESEND_API_KEY isn't set (local dev or before
// Jake adds the key in Vercel), every email is logged to the server console
// instead of sent — the flow still works end-to-end, you just see the
// would-be-email in `npm run dev` output. Swap the sender once the
// rossbuilt.com domain is verified in Resend.

import { Resend } from "resend";
import { supabaseServer } from "./supabase";

const DEV_FROM = "Ross Built <onboarding@resend.dev>";
// Once jakeross838 verifies rossbuilt.com in Resend → swap this and re-deploy.
const PROD_FROM = process.env.RESEND_FROM || DEV_FROM;

// Tiny in-memory cache so we don't hit Supabase on every sendEmail call.
let cachedKey: { value: string | null; at: number } | null = null;
const KEY_TTL_MS = 60_000;

// Resolve the Resend API key from env first, then fall back to a row in
// `public.app_config (key='RESEND_API_KEY')`. The Supabase fallback exists
// because setting a real env var on Vercel needs the project owner's clicks
// in the dashboard, and we want forgot-password / signup emails to work
// without that ceremony.
async function resolveResendKey(): Promise<string | null> {
  const env = process.env.RESEND_API_KEY?.trim();
  if (env) return env;
  if (cachedKey && Date.now() - cachedKey.at < KEY_TTL_MS) return cachedKey.value;
  try {
    const sb = supabaseServer();
    const { data } = await sb
      .from("app_config")
      .select("value")
      .eq("key", "RESEND_API_KEY")
      .maybeSingle();
    const v = (data as { value: string | null } | null)?.value ?? null;
    cachedKey = { value: v, at: Date.now() };
    return v;
  } catch {
    cachedKey = { value: null, at: Date.now() };
    return null;
  }
}

export interface EmailInput {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

export interface EmailResult {
  ok: boolean;
  id?: string;
  error?: string;
  /** If true, the email was logged to console rather than sent (no API key). */
  dev?: boolean;
}

export async function sendEmail(input: EmailInput): Promise<EmailResult> {
  const key = await resolveResendKey();
  if (!key) {
    // Dev fallback — log so the link is recoverable from server output.
    console.log("\n──────── [email · DEV FALLBACK · no RESEND_API_KEY] ────────");
    console.log("  To:      ", input.to);
    console.log("  Subject: ", input.subject);
    console.log("  Text:    ", (input.text ?? "(see HTML below)").slice(0, 800));
    console.log("  HTML:    ", input.html.replace(/<[^>]+>/g, " ").trim().slice(0, 400));
    console.log("─────────────────────────────────────────────────────────────\n");
    return { ok: true, dev: true };
  }
  try {
    const resend = new Resend(key);
    const r = await resend.emails.send({
      from: PROD_FROM,
      to: [input.to],
      subject: input.subject,
      html: input.html,
      text: input.text,
    });
    if (r.error) {
      console.error("[email] resend error:", r.error);
      return { ok: false, error: r.error.message };
    }
    return { ok: true, id: r.data?.id };
  } catch (e) {
    console.error("[email] throw:", e);
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

// Wrap any subject + body in the brand-tinted shell so the email looks like
// it came from Ross Built, not a system alert.
export function brandWrap({
  preheader,
  intro,
  cta,
  ctaUrl,
  body,
}: {
  preheader?: string;
  intro: string;
  cta?: string;
  ctaUrl?: string;
  body?: string;
}): string {
  const button = cta && ctaUrl
    ? `<a href="${ctaUrl}" style="display:inline-block;background:#3B5864;color:#FBFCFD;text-decoration:none;font-family:'Helvetica Neue',Arial,sans-serif;font-size:14px;letter-spacing:0.04em;padding:12px 22px;border-radius:2px;">${cta}</a>`
    : "";
  return `<!doctype html><html><body style="margin:0;padding:0;background:#ECEFF1;font-family:'Helvetica Neue',Arial,sans-serif;color:#3B5864;">
${preheader ? `<span style="display:none;visibility:hidden;opacity:0;height:0;width:0;font-size:1px;line-height:1px;">${preheader}</span>` : ""}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ECEFF1;padding:32px 16px;">
  <tr><td align="center">
    <table role="presentation" width="520" cellpadding="0" cellspacing="0" border="0" style="background:#FBFCFD;border:1px solid #CFD5D8;border-top:3px solid #5B8497;">
      <tr><td style="padding:28px 32px 12px;">
        <div style="font-size:11px;letter-spacing:0.22em;text-transform:uppercase;color:#5B7383;font-weight:600;">Ross Built · Production Cockpit</div>
      </td></tr>
      <tr><td style="padding:4px 32px 0;">
        <p style="margin:0 0 16px 0;font-size:15px;line-height:1.55;color:#3B5864;">${intro}</p>
        ${body ? `<p style="margin:0 0 18px 0;font-size:14px;line-height:1.6;color:#5B7383;">${body}</p>` : ""}
      </td></tr>
      ${button ? `<tr><td style="padding:6px 32px 28px;">${button}</td></tr>` : ""}
      <tr><td style="padding:0 32px 28px;">
        <hr style="border:0;border-top:1px solid #DEE3E5;margin:0 0 14px 0;" />
        <p style="margin:0;font-size:11px;line-height:1.5;color:#8A9AA5;">If you didn't expect this email, ignore it — nothing has changed. Replies aren't monitored.</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>`;
}
