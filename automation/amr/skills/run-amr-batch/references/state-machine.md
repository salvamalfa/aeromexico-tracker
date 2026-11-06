# AMR Batch State Machine

## Atomic Named-Range Fence

Use the unique named range `AMR_GLOBAL_LOCK` over `Control_AMR_Run!A2:G2` as the global lock and fencing token. Named-range names are unique in Sheets. Its client-supplied `namedRangeId` is `amr` plus a UUIDv4 without hyphens, so a deleted token is never reused.

Lease row columns are A Run ID, B State, C Started, D Expires, E Automation ID, F Heartbeat, G Fencing Token ID.

1. Generate `AMR-YYYYMMDD-<uuid-v4>` and capture coordinator start/query date in `America/Mexico_City`.
2. Read lease row 2. If B is `Active`, A/G are nonblank, and D is later than now, stop before mutation.
3. For an expired `Active` lease, require a well-formed G token. In one batch, `deleteNamedRange` using that exact token, clear A/C/D/F/G, set B `Released`, and restore E `amr-batch-runner`. A concurrent old-owner batch either serializes before this recovery or fails atomically afterward.
4. Generate a never-reused token ID. In one atomic batch, `addNamedRange` with name `AMR_GLOBAL_LOCK`, that token ID, and the exact row-2 range; then write A run ID, B `Active`, C start, D start plus six hours, E automation ID, F heartbeat, and G token ID.
5. A duplicate-name error means another coordinator owns/won the lock; re-read row 2 and stop. For an ambiguous response, read row 2: exact own run/token means acquired, another value means lost, and Released means one safe retry with a new token.
6. Re-read row 2 and proceed only when A/G equal the own run/token and B is `Active` with D later than now.
7. Every reservation, retry update, success/failure commit, heartbeat, and other shared mutation must be one Sheets batch whose first request is a no-op `updateNamedRange` for the own token, fixed name, and exact range. If the token was deleted, Sheets rejects the entire batch and none of its later requests apply.
8. Before each fenced batch, also re-read row 2 and require own active/unexpired values. Stop dispatch immediately after ownership loss.
9. Release in one atomic batch with `deleteNamedRange` for the own token followed by clearing A/C/D/F/G and setting B `Released`. If the token is already gone, the whole release fails and cannot clear a successor's lease.

For an ambiguous expired-lease recovery or final release, read row 2 before retrying:

- `Released` with blank A/G: accept success;
- exact own/expired run and token still `Active`: retry the identical delete-and-release batch once;
- a different active run/token: stop; ownership passed and no old-token retry is allowed;
- any malformed mixture: report an integrity blocker and leave the row untouched.

This fence serializes batch runs and queue registration. Lease expiry bounds crash recovery; the named-range ID prevents a delayed prior coordinator from mutating after a successor takes ownership.

## Invocation-State Rules

The Scheduled automation recurrence is the sole authority for when a batch runs. Never gate eligibility on `Control_AMR` column B or any weekday stored in the spreadsheet. A changed Scheduled day or time must work without any spreadsheet or skill edit.

Normalize the queue into one JSON payload before running `queue_decision.py`:

```json
{
  "query_date": "DD/MM/YYYY",
  "now": "RFC3339 timestamp with offset",
  "rows": [{
    "control_row": 2,
    "active": true,
    "status": "Listo",
    "last_attempt_date": "DD/MM/YYYY",
    "last_attempt_timestamp": "RFC3339 timestamp with offset",
    "last_success": "DD/MM/YYYY",
    "current_run_owned": false,
    "foreign_lease_active": false,
    "error_class": null,
    "consecutive": 0,
    "delayed_retry_count": 0,
    "retry_after_timestamp": null,
    "recovery_pass_date": null,
    "manual_force": false
  }]
}
```

Use null/empty optional fields when absent. Derive the two last-attempt fields from H; never invent a timestamp when H contains only a date. Parse error class, consecutive, delayed retry count, retry-after timestamp, and exact `force_once=true` from M. Treat blank/null counters as zero. Normalize legacy `error_class=worker_error` to `infrastructure`. The script output action is authoritative.

| Queue state | Eligible rule |
| --- | --- |
| Inactive | Never. |
| `Pendiente` or blank | Eligible unless it already has a success for the captured query date. `force_once=true` overrides once. |
| `Listo` | Eligible when I is blank or earlier than the captured query date; skip when I equals it. A future I is a review error. |
| `Error` | Eligible when H's local date is earlier than the captured query date. A same-date infrastructure error is eligible exactly once when its ten-minute retry time has arrived. Manual force may override. Existing quarantine rules still apply. |
| `En curso`, current run token | Resume/reconcile; never dispatch a duplicate. |
| `En curso`, another unexpired fence | Skip. |
| `En curso`, no matching active fence and H timestamp at least six hours old | Stale: reconcile writes, then reset only that row to `Pendiente` if neither fare row exists. |
| `En curso` with date-only H strictly before the local date six hours ago | Stale with certainty; reconcile as above. |
| `En curso` with blank/too-recent date-only H | `review_ambiguous_in_progress`; do not dispatch. |

Do not use M as primary truth when structured columns answer the question. M carries concise evidence and the prior failure streak.

## Browser Recovery Gate

Treat one failed in-app Browser connection or worker-tab operation as transient. Pause new reservations, let healthy active workers continue, and perform three fresh Luna-low read-only Browser probes across at least 30 seconds. Each probe may only connect and inventory tabs; it must not navigate or create a tab. Resume the unfinished global queue under the canonical execution profile in `SKILL.md` when any probe succeeds. Declare Browser unavailable only when all three checks fail; preserve each exact reason, checkpoint only owned work, release the fence, and leave the task unarchived. Never browse fares in the coordinator, switch to Chrome, or degrade to another browser surface.

## Aeromexico Circuit Breaker

Treat explicit Aeromexico `Site Maintenance`, `Oops! Something went wrong`, `Please contact your administrator`, and equivalent application-error pages as `error_class=infrastructure`; never persist `worker_error` as an error class.

Open one global circuit when two distinct assignments encounter one of these page errors within a rolling ten-minute window. Then:

1. Stop new reservations and suppress fresh Luna-medium escalations that have not started. Let already-active workers finish and checkpoint their known outcomes.
2. Record infrastructure errors with `delayed_retry=0` and `retry_after=<RFC3339 opened_at+10m>`. Keep untouched jobs pending.
3. Maintain the lease heartbeat and wait passively for ten minutes inside the same coordinator. Do not create another automation, chat, worker, or model turn merely to wait.
4. Re-read lease and queue, run `queue_decision.py`, and dispatch one oldest eligible infrastructure error as a fresh Luna-low probe.
5. Probe success closes the circuit. Commit it, then resume only unfinished jobs under the canonical global-pool capacity, ordering, and launch pacing in `SKILL.md`.
6. Probe failure keeps the circuit open. Set `delayed_retry=1` on all same-run infrastructure errors, leave untouched jobs recoverable, checkpoint, release the fence, and finish without another same-date cooldown.

Allow at most one circuit cooldown/probe cycle per query date. Availability, contract, cleanup, integrity, login, CAPTCHA, and Browser-connection failures do not count toward this Aeromexico page-error circuit. Only enter the cooldown when enough time remains before the five-hour reservation deadline to wait, probe, and checkpoint safely.

## Outcomes And Retries

Primary fare workers use Luna low. Normalize blank queue L to zero, then increment it and refresh H/J/K/M before each fresh worker dispatch, including Luna-medium escalation and +1. Before reservation, parse the preserved error streak plus force marker; reservation M carries the streak in `prior_*` and omits force/request fields, consuming only the one-shot marker. Same-worker JSON re-emission performs no browsing and does not increment L.

For `dispatch_delayed_retry`, reserve with `retry_kind=delayed` and preserve `prior_delayed_retry` plus `prior_retry_after` in M. If that fresh worker fails, write the terminal error with `delayed_retry=prior_delayed_retry+1`; if it succeeds, use the normal full or partial success checkpoint. Never dispatch a delayed retry when the resulting count would exceed one.

| Outcome | Coordinator action |
| --- | --- |
| Valid full fare success, any cleanup status | Commit exactly one Main/Premier pair, formulas, and `Listo`; clear M and record cleanup `error` only as a run warning. |
| Valid one-cabin partial success, any cleanup status | Commit the available cabin as one compact row at the insertion cursor, advance the cursor by one, ensure formulas for the written row, set `Listo`, and persist the exact partial marker in M. Do not allocate an empty row, retry, or discard the available cabin. |
| JSON syntax/key error after completed browsing | Ask the same worker once to re-emit from memory. Then retry once in a fresh Luna medium worker. |
| Infrastructure, contamination, CAPTCHA, incomplete fare, or timeout | Retry once in a fresh Luna medium worker for the identical assignment, unless the global Aeromexico circuit has opened. |
| Confirmed `No hay vuelos disponibles` on base date | Dispatch one fresh Luna low worker with both legs shifted exactly +1 day. |
| Confirmed no availability after +1 | Terminal `Error` for this query date; retry on the next Scheduled invocation whose captured local date is later. Never try +2. |
| Cleanup error or unknown with otherwise valid fares | Preserve and commit fares, continue the global pool, and retry exact run-owned tab cleanup during finalization. Never create a queue error or fare retry solely for cleanup. |
| Unknown spreadsheet commit | Use the read-after-write matrix in `sheets-protocol.md`; never blind-replay. |

Set M for terminal errors as:

`error_class=<availability|infrastructure|contract|cleanup|integrity>; code=<short_code>; consecutive=<n>; delayed_retry=<0|1>; retry_after=<RFC3339|null>; query_date=<DD/MM/YYYY>; run=<run_id>; evidence=<concise text>`

Capture prior M before reservation overwrites it. Compute `consecutive` once per query run:

- availability: always 1 and never quarantined across query dates;
- infrastructure/contract/cleanup/integrity: prior same class on an earlier query date means prior n + 1; same query date keeps prior n; missing/different class starts at 1;
- full success clears M; partial success replaces M with a non-error partial marker. Either resets the prior failure streak;
- quarantine a nonavailability class at n >= 3 until manual review/force.

## Automatic Recovery Sweep

After the normal global queue drains, and only when at least 30 minutes remain before the five-hour reservation deadline, run `queue_decision.py` again with `allow_recovery_sweep: true`. Parse `recovery_pass_date` from M into every normalized row. Dispatch eligible recovery jobs through the same canonical ordered pool defined in `SKILL.md`.

- `dispatch_recovery` may include active infrastructure, contract, or cleanup errors from the current run or an earlier run, even when their ordinary streak is quarantined.
- Never include availability or integrity errors.
- Never dispatch when `recovery_pass_date` already equals the captured query date.
- Mark the reservation/detail with `recovery_pass_date=<query_date>` before dispatch and preserve that marker on terminal failure. A success clears M normally.
- Give the recovery assignment one fresh Luna-low attempt and the normal sole Luna-medium escalation. Do not start another recovery sweep on the same query date and do not require `force_once` or user intervention.

## Runtime Bounds

- Stop reserving new jobs five hours after coordinator start.
- Let active workers finish within their individual timeout.
- Checkpoint known results, release the fence, and leave unfinished jobs for recovery.
- Never switch to coordinator browsing or another browser surface.
