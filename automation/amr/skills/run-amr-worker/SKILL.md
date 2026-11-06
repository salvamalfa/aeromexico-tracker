---
name: run-amr-worker
description: Execute exactly one coordinator-assigned Aeromexico AMR fare search in the in-app Browser and return every schema-validated available Main/Premier fare, including a one-cabin partial result, with explicit tab-cleanup status. Use only for one-job workers spawned by run-amr-batch or an explicit isolated benchmark; never read or write Google Sheets or the AMR queue.
---

# Run AMR Worker

## Contract First

Read these files before any browser action:

- `references/worker-assignment.schema.json`
- `references/worker-result.schema.json`

Accept exactly one assignment JSON object that validates against the assignment schema. Copy every identity and date field exactly. If the assignment is absent, invalid, or accompanied by a second job, return a contract error without browsing. When no Browser session or tab was created, cleanup is `ok` by construction; do not initialize Browser solely to clean up nothing.

Never calculate dates, alter the URL, inspect a queue, use Google Drive or Sheets, call an API, create another agent, or process another route. The coordinator owns dates, retries, validation, and all writes.

Use only `browser:control-in-app-browser` for Aeromexico. Never substitute Chrome, Computer Use, web search, or an independent Playwright service.

## Browser Isolation

1. Treat `browser_lane` only as an immutable assignment identity label. It does not represent a Region, pool slot, or user profile.
2. Create exactly one worker-owned temporary tab, retain its exact identity/binding for cleanup, and reuse it.
3. Never touch user-owned tabs or another worker's tab. Do not inspect cookies, local storage, passwords, profiles, or session stores.
4. The coordinator owns global capacity, ordering, and launch pacing; workers never launch or coordinate sibling jobs.
5. Open exactly `clean_url`. Confirm destination and both dates from the URL before selecting a fare.
6. Prefer snapshots, DOM text, locators, and read-only JavaScript evaluation. Use a screenshot only when a green promotion badge cannot be determined from DOM text or computed style. Never zoom.
7. Dismiss cookie, newsletter, login, and promotional overlays. Do not log in.

## Availability

If the page explicitly says `No hay vuelos disponibles`, reload the same clean URL once in the same tab. Only after the second clean load confirms the same message may the job return that exact availability error.

Do not classify slow loading, route contamination, a stale page, Browser disconnection, CAPTCHA, or login blocking as no availability. Return a concise exact worker error instead. Never change either date; the coordinator owns the sole +1-day assignment.

Search Main and Premier independently. When fare `Clasica` is explicitly unavailable for either leg of one cabin after confirming the correct mode and cabin, mark only that cabin unavailable and continue or preserve the other cabin. Cabin-level unavailability is not permission to omit an unreadable checkout value: a selected cabin with incomplete, ambiguous, or unverified values remains a worker error.

## Main

1. Ensure payment mode is `Puntos` and cabin is `Main`.
2. In page order, select the first available nonstop outbound flight and fare `Clasica`. If no nonstop is available, select the first available flight with stops.
3. Capture its departure time as `HH:MM`.
4. Inspect only that selected flight container. Promotion is `Si` when it contains `Promo`, `Promocion`, or a green promotion badge; otherwise `No`.
5. Apply the same page-order, nonstop-first, `Clasica` rule to the return and capture its departure time and promotion.
6. Combined Main promotion is `Si` when either direction is promotional; otherwise `No`.
7. In the points checkout capture `carrier_points` and `award_taxes_mxn`. `award_taxes_mxn` is the exact MXN amount labeled `Impuestos y Tasas` in points mode. Do not use the points-checkout grand total, do not include or add any carrier MXN component, and do not reuse the money-mode taxes.
8. Select `Pagar con dinero` and capture `cash_carrier_mxn`, `cash_taxes_mxn`, and `points_accrual`.

Use checkout values, not fare-card teaser prices. Return finite nonnegative JSON numbers without display separators, currency labels, or point labels.

## Premier

1. Select `Cambiar vuelo`, then ensure mode `Puntos` and cabin `Premier`.
2. Repeat the complete selection independently: first nonstop in page order, otherwise first with stops, always `Clasica`, for both legs.
3. Capture Premier times and combined promotion independently.
4. Repeat the points checkout and then `Pagar con dinero` checkout.

Never reuse any Main time, promotion, or amount for Premier. Do not estimate a missing value. If exactly one cabin is fully captured and the other cabin is explicitly unavailable, return the captured cabin as a partial result instead of discarding it.

## Result

Build exactly the strict object defined by `worker-result.schema.json`. A successful shape is:

```json
{
  "run_id": "<copy>",
  "region": "<copy>",
  "browser_lane": "<copy>",
  "worker_status": "ok",
  "worker_error": null,
  "cleanup_status": "ok",
  "cleanup_error": null,
  "job": {
    "control_row": 2,
    "order": 1,
    "destination": "MTY",
    "months": 1,
    "query_date": "DD/MM/YYYY",
    "departure_date": "DD/MM/YYYY",
    "return_date": "DD/MM/YYYY",
    "date_shift_days": 0,
    "status": "ok",
    "error": null,
    "main": {
      "outbound_fare": "Clasica",
      "return_fare": "Clasica",
      "outbound_time": "HH:MM",
      "return_time": "HH:MM",
      "promotion": "Si",
      "carrier_points": 0,
      "award_taxes_mxn": 0,
      "cash_carrier_mxn": 0,
      "cash_taxes_mxn": 0,
      "points_accrual": 0
    },
    "premier": {
      "outbound_fare": "Clasica",
      "return_fare": "Clasica",
      "outbound_time": "HH:MM",
      "return_time": "HH:MM",
      "promotion": "No",
      "carrier_points": 0,
      "award_taxes_mxn": 0,
      "cash_carrier_mxn": 0,
      "cash_taxes_mxn": 0,
      "points_accrual": 0
    }
  }
}
```

For confirmed no availability, keep `worker_status: "ok"`, set job status/error to `"error"`/`"No hay vuelos disponibles"`, and set both cabins to null.

For one-cabin availability, keep `worker_status: "ok"` and `worker_error: null`, set job status to `"partial"`, preserve the complete available cabin, and set only the unavailable cabin to null. Use exactly `"Premier: No disponible"` when Main is present or `"Main: No disponible"` when Premier is present. Never use `partial` when both cabins are present, both are absent, or a cabin was merely incomplete.

For browsing or contract failure, set both worker and job status to `error`, use the same concise error string in `worker_error` and `job.error`, and set both cabins to null.

## Mandatory Cleanup

Hold the completed payload in memory. Close only the retained exact Browser tab. On a transient close failure, retry that same exact-tab close once without any intervening browser action, then perform one read-only tab inventory. Cleanup is proven when the exact worker-owned tab is absent; user-owned tabs and other worker tabs may remain. The verifying inventory read must be the final browser action. Never close by title, URL pattern, positional index, or a broad cleanup action.

- Exact-tab close plus inventory proves the worker tab is absent: set `cleanup_status` to `ok` and `cleanup_error` to null.
- The exact Browser tab cannot be proven absent: set `cleanup_status` to `error` and `cleanup_error` to a concise closure warning. Preserve `worker_status`, `worker_error`, `job.status`, `job.error`, Main, and Premier exactly as determined by browsing. Cleanup never changes fare validity.

Always return every complete validated cabin when browsing succeeded, including a one-cabin partial result, regardless of cleanup status. A leftover tab is operational residue for the coordinator to retry closing; it is not a fare error.

Return exactly one JSON object, with no Markdown fence, prose, or extra key.
