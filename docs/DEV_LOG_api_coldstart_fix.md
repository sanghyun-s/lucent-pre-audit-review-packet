# DEV LOG — The `body stream already read` cold-start fix

**Date:** 2026-07-31
**Area:** `frontend/lib/api.js` (transport wrapper) · deployment (Render free tier)
**Commits:** `cf05146` (core fix) → follow-up polish (graceful abort message)
**Status:** Resolved · verified end-to-end on the worst-case input

---

## Symptom

Running the deployed app, an upload would sometimes fail with:

```
Failed to execute 'text' on 'Response': body stream already read
```

It was **intermittent**, which made it feel random and hard to trust. Two patterns eventually stood out, and they turned out to be the whole key:

- It hit hardest on `sample_gl_high_risk.csv` — my densest ledger (800 rows, ~100 flagged), i.e. the request that makes the backend work the longest.
- It hit on the **first run after the app had been idle**, and once I'd run a few files and everything was warm, even `high_risk` went through fine.

## The first (partial) diagnosis — a real bug, but not the whole story

Reading `lib/api.js`, I found a genuine defect: both `analyze()` and `generateNarratives()` had a double-read in their error path —

```js
try {
  detail = (await r.json()).detail;   // consumes the body
} catch {
  detail = await r.text();            // consumes it AGAIN → "body stream already read"
}
```

A `fetch` response body is a one-time stream. If `.json()` runs and fails, the body is already spent, so the fallback `.text()` throws exactly this message. That was real and worth fixing — so I centralized transport into one `request()` helper that reads the body **exactly once**, and pushed it as `cf05146`.

**But the deployed fix didn't stop the error.** That was the important moment: the same message came back even though the double-read was gone. It forced me to stop assuming and actually rule things out.

## Ruling it out, one fact at a time

Instead of guessing, I checked each layer and kept the evidence:

- **Was the fix even deployed?** Render showed the live deploy was commit `cf05146` by name. So it wasn't a stale build or a cached bundle — the new code *was* running.
- **Was there a second file with the old pattern?** A repo-wide grep for `.json()` / `.text()` came back with hits only in `.bak` backup files; the live `FlaggedTable.jsx` routes through the wrapper and has no raw `fetch`. So no live code had a double-read.
- **Was the backend healthy?** Hitting it directly:
  - `/` → `{"detail":"Not Found"}` (correct — no route at root; proves FastAPI is answering)
  - `/api/healthz` → `{"status":"ok","version":"0.4.1"}`
  - `/api/options` → full, correct config JSON
  So the backend was alive and serving the exact routes the frontend calls.
- **Was the frontend→backend URL wired right?** `NEXT_PUBLIC_API_BASE_URL` points at the backend's public `.onrender.com` URL; the earlier `036da2c` commit had already fixed an `ENOTFOUND` from using Render's internal hostname.

Every server-side possibility came back clean. That's what finally pointed at the real cause.

## Root cause

It was **never a live code bug** after `cf05146`. The message was a *symptom* of a **free-tier cold start**:

1. Render spins the backend down after idle (its own dashboard warns: *"can delay requests by 50 seconds or more"*).
2. On the first request after idle, the **heaviest file** (`high_risk`) takes long enough that the request's timeout fires and **aborts the fetch**.
3. The abort tears down the response stream *while `r.text()` is mid-read*. A disturbed stream can't be read again — so the browser reports `body stream already read`.

So the exact trigger was **slowest file × sleepiest server**. Lighter files finished before the timeout; a warm server finished fast. That's precisely the pattern I'd observed but hadn't yet explained.

## The fix

Two layers, both in `lib/api.js`:

1. **Read the body exactly once** (`await r.text()`), then `JSON.parse` — an error response can no longer trigger the double-read. (Shipped in `cf05146`.)
2. **One automatic retry** on a cold-start-style failure (gateway 5xx, network error, or timeout) after a short wait, with a 90s window. Safe because `/api/analyze` and `/api/narratives` are **stateless** — re-sending can't double-write. The first request wakes the server; the retry lands on a now-warm one.
3. **Graceful message** (polish): if a transient failure outlives the retry, the user sees plain English —
   > "The analysis server took too long to respond — it may be waking up. Please try again in a moment."

   — instead of the raw stream/network error.

Kept the timeout at **90s** deliberately: a cold `high_risk` run completes within it, so the retry usually succeeds rather than falling through to the message.

## Verification

Ran the exact combination that used to fail — `sample_gl_high_risk.csv` + Balanced sensitivity — on a cold backend, end to end, clean:

- 800 transactions analyzed · 94 flagged (11.8%) · Overall risk **Elevated**
- Data integrity: 4 checks pass
- Feature firing reconciles with the planted patterns (101 round-number, 76 weekend, 94 missing-description, 95 new-vendor, 117 near-threshold)
- Qualitative override firing as designed (89 fraud-risk flags; flagged rows show co-occurrence + Override)
- AI layer: **10 GPT / 0 fallback** — every memo came from the live model and passed the validator

The numbers line up with the README validation matrix for the high-risk profile, so both the request path *and* the engine behaved correctly.

## Housekeeping done alongside

- Moved scattered `*.bak` / `*.bak.<timestamp>` snapshots out of `components/` and `lib/` into an `_backups/` folder outside the source tree; broadened `.gitignore` to `*.bak.*` so timestamped backups can't be committed.

## Note-only (left as-is, not defects)

- `_backups/` sits beside `frontend/`; gitignore the folder if it shows as untracked and shouldn't be versioned.
- `jsconfig.json` shows a VS Code Problems entry: `baseUrl` is deprecated and stops working in **TypeScript 7.0**. This project has no TypeScript, the app resolves `@/…` imports fine, and TS 7 isn't out — so it's a cosmetic, forward-looking hint. Removing `baseUrl` silences it but Next 14's alias resolution can depend on it, so leave it until a future `tsconfig.json` migration.

## Lessons

- **"Same error after the fix" is information, not failure.** It was the signal that the double-read wasn't the (only) cause and that I needed to rule out layers instead of re-reading the same file.
- **A property of the hosting tier can masquerade as a code bug.** The cold-start timeout *presented* as a stream error. Separating "bug in my code" from "behavior of the free tier" was the crux, and it took deliberately checking deploy status, backend health, and URL wiring to get there.
- **Diagnose from evidence, not vibes.** Every step forward came from a concrete output — the live commit hash, a grep result, a direct `curl` to `/api/healthz` — not from assuming.
- **Testing cadence matters on a free tier.** Hammering every test back-to-back on a service that sleeps *creates* the cold-start condition. As the project's manager that thoroughness is the right instinct, but on a sleeping backend I should space runs out (or keep it warm) so I'm testing the app, not the spin-up.
- **Backups belong outside the source tree.** `.bak` files next to real source are noise at best and a tooling hazard at worst.

## If this ever recurs

The remaining root cause is the cold start itself, not the code. Options, in order of preference for a portfolio project:

1. Accept it — a free-tier wake-up is normal and defensible; the retry + friendly message now handle it gracefully.
2. Keep the backend warm — a scheduled `GET /api/healthz` every ~10 min. Removes the condition entirely, at the cost of an external dependency to maintain.
3. Upgrade off the free tier — same effect, with money instead of a cron.
