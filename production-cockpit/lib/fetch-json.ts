// fetchJson — fetch + parse a JSON API response, but tolerate the NON-JSON
// bodies a platform returns when a function times out or crashes. On Vercel a
// timeout returns a 504 with a text/plain body like:
//   "An error occurred with your deployment\n\nFUNCTION_INVOCATION_TIMEOUT..."
// Calling res.json() on that throws "Unexpected token 'A'... is not valid JSON",
// which is what users saw on long transcript imports. This reads the body as
// text first, parses defensively, and throws a clear, human message instead.
//
// Contract: resolves to the parsed object on success; throws Error(message) on
// any failure (non-OK status, { ok:false }, or a non-JSON body). Callers keep
// their existing try/catch → setError(err.message).

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- JSON APIs are dynamic; callers narrow as needed (mirrors res.json()'s any).
export async function fetchJson<T = any>(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(input, init);
  } catch (e) {
    throw new Error(
      `Network error — couldn't reach the server. ${e instanceof Error ? e.message : ""}`.trim()
    );
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null; // non-JSON body (timeout/crash page, HTML, etc.)
    }
  }

  if (data === null || typeof data !== "object") {
    const isTimeout = res.status === 504 || /TIMEOUT|timed? ?out/i.test(text);
    throw new Error(
      isTimeout
        ? "The request timed out. A very long meeting can take a while to process — try again, or split it into smaller transcripts."
        : `Server error (HTTP ${res.status}). Please try again.`
    );
  }

  const obj = data as { ok?: boolean; error?: string };
  if (!res.ok || obj.ok === false) {
    throw new Error(obj.error || `Request failed (HTTP ${res.status}).`);
  }
  return data as T;
}
