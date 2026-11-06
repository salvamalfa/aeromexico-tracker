---
name: create-amr-automation
description: Register or update an Aeromexico AMR fare-check job for a MEX destination and a 1, 3, or 6 month departure offset in the unified Control_AMR Google Sheet queue. Use when the user invokes /create-amr-automation or asks to add AMR tracking for a destination such as FCO, JFK, MTY, or MAD.
---

> **Repository reference copy — not the installed runtime skill.** This source
> copy is for review and version control only. Before any execution, resolve all
> `{{AMR_*}}` placeholders from an authorized local manifest. Never install or
> activate this copy automatically. The installed skills remain the runtime
> source of truth; this repository copy does not change any launcher or schedule.

# Create AMR Automation

Treat every destination/offset as a queue job handled by the single `AMR Batch Runner`, never as a direct destination-specific fare automation.

## Fixed Resources

- Spreadsheet: `AMR POINTS VALUE`
- Spreadsheet ID: `{{AMR_SPREADSHEET_ID}}`
- Queue: `Control_AMR`, sheet ID `{{AMR_QUEUE_SHEET_ID}}`
- Lease: `Control_AMR_Run`, sheet ID `{{AMR_LEASE_SHEET_ID}}`
- Global fence: unique named range `AMR_GLOBAL_LOCK` over `Control_AMR_Run!A2:G2`

Use connected Google Drive Sheets tools only. Never use an API key, service account, local workbook, browser-based Sheets editing, or the standalone Spreadsheets skill.

## Register Safely

1. Parse and uppercase one three-letter IATA destination. Normalize the offset to exactly 1, 3, or 6 calendar months.
2. Scheduling belongs exclusively to the AMR Batch Runner in Scheduled. Ignore legacy column B and leave it blank for new rows. Classify the destination with the exact Spanish Region taxonomy already used by the live queue, such as `Europa`, `Norteamérica`, `México`, `Asia`, or `Sudamérica`; verify unfamiliar codes before mutation. Region is a lane label, not a scheduling rule, and any nonblank, consistently spelled live Region value is contract-valid.
3. Read `../run-amr-batch/references/state-machine.md` and atomically acquire the same named-range fence, using automation ID `create-amr-automation`. If another valid fence/lease is active, do not mutate or create a scheduler.
4. After winning the lease, read spreadsheet metadata and the bounded populated `Control_AMR!A:M` range. Match destination plus month offset and require zero or one match.
5. Immediately before queue writing, re-read the fence/lease and full bounded queue. Require ownership and re-run the match; this is the concurrency/idempotency check.
6. Existing match: set A true and update B only when explicitly requested. For an explicit immediate rerun, set G `Pendiente`; preserve all existing non-force M fields (especially `error_class`, `consecutive`, and `query_date`), remove any older force/request fields, then append `force_once=true; requested_at=<RFC3339>; requested_by=create-amr-automation`. Otherwise preserve G/M. Use a fenced batch and field masks that preserve every other cell.
7. No match: choose the first fully empty A:M row after the contiguous queue block, set C to max existing numeric order plus one, and use a fenced batch to write A true, C order, D region, E destination, F months, G `Pendiente`, L zero; leave B/H/I/J/K blank. Set M to the same `force_once` marker only when an immediate first run was explicitly requested; otherwise leave it blank.
8. Read back the exact row and complete destination/month match set. Require exactly one queue match and intended values. Never delete or silently repair duplicates; report an integrity error.
9. Release only the owned fence in a final block.

The `AMR Batch Runner` Scheduled RRULE is the sole scheduling authority. Queue column B is legacy and never decides whether a route is due. Never mutate the schedule from this registration workflow and never create a recovery-day or destination-specific scheduler.

Direct standalone prompts are intentionally unsupported because they bypass the lease, strict worker contract, duplicate guard, formula propagation, and idempotent commit protocol. When the user explicitly asks for a standalone destination task, explain that it must remain a queue job and register it through this path.

## Examples

- `/create-amr-automation para MTY 6 meses` registers or reactivates `MTY-6M` for the next eligible batch run.
- `crea AMR para BOG 3 meses` registers or updates `BOG-3M` in the `Sudamérica` lane without changing the batch schedule.
