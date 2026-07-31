// lib/api.js — thin fetch wrapper for the FastAPI endpoints.
// Calls go to /api/* which is proxied to the FastAPI server in dev (see next.config.js)
// and to NEXT_PUBLIC_API_BASE_URL in production.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Owns transport for every endpoint. Three guarantees:
//   1. The response body is read EXACTLY once, so an error response can never
//      trigger "Failed to execute 'text' on 'Response': body stream already read".
//   2. One automatic retry on a cold-start-style failure (gateway 5xx, network
//      error, or timeout) after a short wait, to survive a sleeping free-tier
//      backend waking up on the first request.
//   3. If a transient failure outlives the retry, the user sees a plain-English
//      message ("server waking up / can't reach server"), never a raw stream or
//      network error.
//
// Retrying is safe here specifically because /api/analyze and /api/narratives are
// stateless — no persistence, no side effects — so re-sending cannot double-write.
async function request(url, opts = {}, { retries = 1, timeoutMs = 90000 } = {}) {
  for (let attempt = 0; ; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetch(url, { ...opts, signal: ctrl.signal });
      clearTimeout(timer);

      const raw = await r.text(); // read once, whatever the status
      if (r.ok) return raw ? JSON.parse(raw) : null;

      // Likely a waking server (502/503/504) — wait briefly and retry once.
      if (r.status >= 500 && attempt < retries) {
        await sleep(3000);
        continue;
      }

      // Surface the real error: prefer FastAPI's {detail: ...} if the body is JSON.
      let detail = raw;
      try {
        detail = JSON.parse(raw).detail ?? raw;
      } catch {
        /* body wasn't JSON — keep raw text */
      }
      throw new Error(`${url} failed (${r.status}): ${String(detail).slice(0, 300)}`);
    } catch (err) {
      clearTimeout(timer);
      // AbortError = our timeout fired; TypeError = network/DNS/CORS failure.
      const transient = err.name === "AbortError" || err instanceof TypeError;
      if (transient && attempt < retries) {
        await sleep(3000);
        continue;
      }
      // Out of retries. Turn a timeout / network failure into a human message —
      // on a free-tier host this is almost always the backend waking from idle.
      if (err.name === "AbortError") {
        throw new Error(
          "The analysis server took too long to respond — it may be waking up. Please try again in a moment.",
        );
      }
      if (err instanceof TypeError) {
        throw new Error(
          "Couldn’t reach the analysis server. Check your connection and try again.",
        );
      }
      throw err; // anything else (real 4xx/5xx with a body): surface as-is
    }
  }
}

export async function fetchOptions() {
  return request("/api/options");
}

export async function analyze({
  file,
  entityType,
  benchmarkFigure,
  detectionSensitivity,
  periodStart,
  periodEnd,
}) {
  const fd = new FormData();
  fd.append("csv", file);
  fd.append("entity_type", entityType);
  fd.append("benchmark_figure", String(benchmarkFigure));
  fd.append("detection_sensitivity", detectionSensitivity);
  fd.append("period_start", periodStart);
  fd.append("period_end", periodEnd);

  return request("/api/analyze", { method: "POST", body: fd });
}

// Generate Top-N audit memos for already-flagged rows. Mirrors analyze():
// owns the transport only; callers handle UI state and response mapping.
export async function generateNarratives({ rows, entityContext, topN }) {
  return request("/api/narratives", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rows,
      entity_context: entityContext || {},
      top_n: topN,
    }),
  });
}
