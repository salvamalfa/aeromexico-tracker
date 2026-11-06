---
name: run-amr-batch
description: Coordinate scheduled, recovery, or manual Aeromexico AMR queue runs from Control_AMR. Use for fenced queue selection, globally ordered dispatch of isolated in-app Browser workers, strict result validation, and serialized Google Sheets commits; use run-amr-worker instead for one standalone assigned fare search.
---

> **Repository reference copy — not the installed runtime skill.** This source
> copy is for review and version control only. Before any execution, resolve all
> `{{AMR_*}}` placeholders from an authorized local manifest. Never install or
> activate this copy automatically. The installed skills remain the runtime
> source of truth; this repository copy does not change any launcher or schedule.

# Run AMR Batch

## Purpose And Fixed Resources

Process due `Control_AMR` jobs into compact, validated `Vuelos` rows while preserving an auditable queue, a single global lease, and exact worker isolation.

- Spreadsheet ID: `{{AMR_SPREADSHEET_ID}}`
- Queue: `Control_AMR`, sheet ID `{{AMR_QUEUE_SHEET_ID}}`
- Data: `Vuelos`, sheet ID `{{AMR_DATA_SHEET_ID}}`
- Lease: `Control_AMR_Run`, sheet ID `{{AMR_LEASE_SHEET_ID}}`
- Global fence: unique named range `AMR_GLOBAL_LOCK` over `Control_AMR_Run!A2:G2`
- Time zone: `America/Mexico_City`
- Origin: `MEX`
- Scheduling authority: the Scheduled automation recurrence only; ignore legacy queue column B

## Canonical Execution Profile

Treat this section as the single source of truth for dispatch topology. References may describe how to pause or resume the pool but must not redefine these values.

- Topology: one globally ordered worker pool (`mode=global-pool`)
- Capacity: at most three active fare assignments
- Order: ascending numeric `Control_AMR` column C, then ascending physical queue row
- Region: assignment metadata only; never partition, reserve, or throttle work by Region
- Launch pacing: at least 30 seconds between every fresh worker launch across the entire run, including primary workers, escalations, +1-day fallbacks, circuit probes, and recovery attempts
- Slot lifecycle: keep a job in its pool slot through its allowed retries; release the slot only after the result is validated, committed or checkpointed, and the worker is closed
- Primary worker: `gpt-5.6-luna`, reasoning `low`
- Escalation worker: `gpt-5.6-luna`, reasoning `medium`

The ordering guarantee applies to fresh job starts. Parallel jobs may finish and commit in a different order; do not delay a validated commit merely to reproduce queue order in `Vuelos`.

## Tools And Ownership

Use connected Google Drive Sheets tools for every spreadsheet read and write. Never use an API key, service account, local workbook, browser-based Sheets editing, or the standalone Spreadsheets skill.

Use `browser:control-in-app-browser` only in isolated fare workers and read-only capability probes. The coordinator must never browse fares, manipulate worker tabs, switch to Chrome or Computer Use, or perform broad cleanup.

Only the coordinator may select or reserve queue rows, calculate dates, access Drive, validate assignments/results, choose insertion rows, copy formulas, checkpoint jobs, reconcile duplicates, release the fence, or archive the task. Each worker receives exactly one assignment and never receives this coordinator skill, Drive access, or permission to create agents.

## Required References And Deterministic Scripts

Read these references before the first mutation:

- [state-machine.md](references/state-machine.md) for the lease, eligibility, retries, circuit breaker, quarantine, recovery sweep, and runtime bounds
- [sheets-protocol.md](references/sheets-protocol.md) for bounded reads, field masks, reservation/commit batches, formulas, idempotency, and final reconciliation
- `../run-amr-worker/references/worker-assignment.schema.json`
- `../run-amr-worker/references/worker-result.schema.json`

Run these scripts; do not reimplement their logic:

- `python scripts/amr_dates.py --query-date <DD/MM/YYYY> --months <1|3|6> --shift-days <0|1>`
- Pipe the normalized queue to `python scripts/queue_decision.py --stdin`
- Pipe each assignment to `python scripts/validate_worker_result.py --stdin --assignment-only --emit-worker-prompt`
- Pipe `{"assignment": ..., "result": ...}` to `python scripts/validate_worker_result.py --stdin` before every result checkpoint

## Workflow

### 1. Preflight And Fence

1. Capture one query date from the actual calendar in `America/Mexico_City`; retain it for the entire run, including across midnight.
2. Generate a UUIDv4 run ID matching `AMR-YYYYMMDD-<uuid-v4>`.
3. Perform the cheap read-only lease/queue preflight and classify every populated queue row. If no row can require work on this query date, finish without acquiring the fence or initializing Browser.
4. Otherwise acquire and verify the named-range fence and six-hour lease exactly as defined in `state-machine.md`.
5. Re-read the authoritative queue under the fence. Preserve actual 1-based row numbers and reject duplicate destination-plus-month keys before dispatch.

### 2. Reconcile Before Dispatch

Reconcile every due job against bounded `Vuelos!A:N`, regardless of queue status. Accept only:

- zero matching identity rows as eligible work;
- exactly one Main plus one Premier row as an already committed full success; or
- exactly one cabin row backed by a matching `partial=true` queue marker as an already committed partial success.

Treat orphan cabins, duplicate tariffs, marker mismatches, extra matches, future dates, and ambiguous `En curso` rows according to the references. Verify or recover the insertion cursor and formula capacity before reserving a job.

### 3. Browser Gate

Run the isolated read-only in-app Browser probe before the first reservation. If it fails, apply the Browser recovery gate from `state-machine.md`. Never degrade to coordinator browsing or another browser surface.

### 4. Ordered Global Dispatch

1. Sort eligible jobs by numeric column C, using physical queue row as the stable tiebreaker.
2. Fill up to three pool slots from the head of that queue, enforcing the global 30-second fresh-launch interval.
3. Immediately before each reservation, re-read the exact queue row and lease. Build dates with `amr_dates.py`, validate the complete assignment, and use the emitted ASCII-safe worker prompt unchanged.
4. Reserve with `mode=global-pool`, read back the exact reservation, then launch one fresh worker.
5. Keep the slot assigned to that job through any allowed same-job retry. When the job is terminally committed/checkpointed and its worker is closed, fill the free slot with the next ordered job, again respecting the global launch interval.
6. Serialize every Sheets mutation through the coordinator-owned critical section even while browsing remains parallel.
7. Stop reserving new jobs five hours after coordinator start; let active workers finish within their individual timeout.

### 5. Validate, Retry, And Commit

Validate the exact assignment/result pair before acting. Never infer missing fields, scrape JSON from prose, repair a worker object, or write an unvalidated result.

Apply the retry and circuit rules from `state-machine.md`. Same-worker JSON re-emission performs no browsing and is not a fresh launch. All new workers—including escalations and fallbacks—remain subject to the canonical capacity and launch pacing.

Commit valid `ok` and `partial` results using the atomic protocol in `sheets-protocol.md`, regardless of cleanup status. Write only available cabins, contiguously in Main-then-Premier order, and advance the cursor by the exact number of written rows. Never allocate a blank row for an unavailable cabin or discard a complete cabin because the other cabin is unavailable.

For a terminal failure, update only the queue fields permitted by the Sheets protocol. Preserve assignment evidence and continue the global pool unless a shared integrity or fence failure requires a global stop.

### 6. Recovery Sweep And Finish

After the normal global queue drains, run the single bounded automatic recovery sweep defined in `state-machine.md` when enough time remains. Recovery jobs use the same ordered pool, capacity, pacing, validation, and commit rules.

Before releasing the fence:

- reconcile every changed queue row and newly written A:R row;
- require the exact full or partial cabin identity for each success;
- require O:R formulas through the final inserted row;
- require no internal A:N gap before the cursor and no run-owned `En curso` row;
- verify cleanup was attempted for every worker and report residue only as a warning; and
- verify no duplicate identity or out-of-range write was introduced.

Compact an internal gap only through the fenced procedure in `sheets-protocol.md`. Release only this run's lease in a final block. Archive only when all fare results and Sheets mutations reconcile and no fare, availability, contract, infrastructure, or integrity error remains.
