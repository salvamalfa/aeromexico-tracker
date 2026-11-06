> **Repository reference copy — not the installed runtime skill.** This source
> copy is for review and version control only. Before any execution, resolve all
> `{{AMR_*}}` placeholders from an authorized local manifest. Never install or
> activate this copy automatically. The installed skills remain the runtime
> source of truth; this repository copy does not change any launcher or schedule.

# AMR Google Sheets Protocol

## Fixed Sheets

- Spreadsheet ID: `{{AMR_SPREADSHEET_ID}}`
- Queue: `Control_AMR`, sheet ID `{{AMR_QUEUE_SHEET_ID}}`
- Data: `Vuelos`, sheet ID `{{AMR_DATA_SHEET_ID}}`
- Lease: `Control_AMR_Run`, sheet ID `{{AMR_LEASE_SHEET_ID}}`
- Fence name/range: `AMR_GLOBAL_LOCK` over `Control_AMR_Run!A2:G2`
- Insertion cursor: `Control_AMR_Run!B4` (`Next Vuelos Row` in A4)

Use connected Google Drive Sheets tools only. Use raw `batchUpdate` requests with bounded grids and explicit field masks. Never use browser-based Sheets editing, a local workbook, an API key, or a service account.

## Read And Reservation Rules

1. Read metadata, queue, lease, and insertion cursor before mutation. Group reconciliation jobs by query date and use `search_spreadsheet_rows` once per distinct date; filter returned rows locally by destination/departure/return/tariff and cache the compact identity index.
2. Treat B4 as the normal insertion frontier. Require a finite integer row >= 2 and verify enough consecutive A:N rows are fully empty for the current result: two for a full Main/Premier result and one for a partial result. If occupied, scan forward in bounded chunks to the first empty row after the last populated A:N row. Never intentionally fill a historical internal gap.
3. Only when B4 is blank, invalid, points beyond recoverable bounds, or an internal A:N gap exists before it, rebuild and compact the insertion frontier with one full A:N scan. Compaction must preserve populated-row order, move complete A:R rows upward without changing values or formulas, clear only the vacated trailing A:N rows, and update B4 atomically under the fence. Record duplicates or discontinuities as findings; never overwrite a nonempty destination row.
4. Immediately before a reservation, re-read the exact queue row and lease row.
5. Before reservation, build the complete assignment from `amr_dates.py` and require `validate_worker_result.py --assignment-only --emit-worker-prompt` success. Reserve with bounded `updateCells` requests that set G `En curso`; H to the fresh-dispatch RFC3339 timestamp with `America/Mexico_City` offset; J/K to the already-validated assignment departure/return in `DD/MM/YYYY`; L to zero plus one when blank, otherwise the prior finite nonnegative integer plus one; and M to `run=<id>; reserved; region=<region>; mode=global-pool; retry_kind=<normal|delayed|recovery>; date_shift=<0|1>; recovery_pass_date=<date|null>; prior_error_class=<value>; prior_consecutive=<n>; prior_delayed_retry=<n>; prior_retry_after=<timestamp|null>; prior_query_date=<date>`. Preserve I and use `fields: userEnteredValue` only.
6. Capture prior M before overwriting it, then read back G:H/J:M and require every exact value. Require J/K to equal the validated assignment before dispatching its exact emitted worker prompt. Same-worker JSON re-emission does not update H/L; every fresh worker does.

Every mutating batch must begin with the owned-token no-op `updateNamedRange` request from `state-machine.md`. This request and all cell/formula requests are one atomic Sheets batch. A stale token makes the entire operation fail before any cell changes. Execute every Sheets mutation through one coordinator-owned single-writer critical section; never overlap reservation, retry, failure, success, cursor, heartbeat, or release calls across pool slots.

## Formula Capacity

Columns O:R are formula-owned. Workers never touch them; the coordinator must populate them.

Before dispatch, compute the largest possible destination row from the insertion frontier plus two rows per selected job as the safe upper bound. Increase the sheet row count first if needed. Ensure O:R formulas cover that row by copying the nearest preceding verified formula row with `copyPaste` and `pasteType: PASTE_FORMULA`, followed by a bounded `PASTE_FORMAT` for O:R.

For every success, calculate `rows_needed` from the non-null cabins, write those cabin rows contiguously in Main-then-Premier order, and advance B4 by exactly `rows_needed`. Include formula and format `copyPaste` requests for O:R into every written cabin row. No row is allocated for an unavailable cabin. Copy from the immediately preceding verified formula row and stamp D4. After all work, require formulas in every written row and require no internal A:N blank row before B4.

## Success Commit

Before committing, require:

- this run still owns the unexpired named-range fence and lease;
- the exact queue row is still `En curso` with this run ID and assignment dates;
- the exact `rows_needed` target A:N rows are still empty and begin at B4;
- the worker result passed `validate_worker_result.py` with status `ok` or `partial`; cleanup status is not a commit gate;
- a fresh bounded identity search finds zero existing rows for the same query date, destination, departure, and return. Exactly one Main plus one Premier is an already-committed full success. Exactly one cabin row is an already-committed partial success only when queue M contains `partial=true` with the opposite missing cabin, the same query date, and a valid run ID. Any other nonzero count is an integrity error.

Use one `batch_update_spreadsheet` call in this exact order:

1. owned-token no-op `updateNamedRange` fence request;
2. `updateCells` for each available cabin in contiguous Main-then-Premier order, columns A:N, with `fields: userEnteredValue`;
3. bounded `copyPaste` requests for O:R with `pasteType: PASTE_FORMULA` and `PASTE_FORMAT` for each written row;
4. queue `updateCells` for G=`Listo` and I=query date, without touching H/J/K/L. Set M blank for `ok`; for `partial`, set `partial=true; missing=<Main|Premier>; reason=No disponible; query_date=<DD/MM/YYYY>; run=<run_id>`;
5. cursor `updateCells` for B4/D4 to the first row after the compact write/timestamp.

Column K means `Impuestos y Tasas (MXN)`: the exact taxes-and-fees amount displayed in the points checkout. It is not the points-checkout grand total, must not include a carrier MXN component, and is distinct from column M's money-mode taxes.

Read back the exact compact A:R write range, queue G:M, and cursor. For partial success, require exactly one written cabin row and the marker to identify the absent cabin. Require the next cursor row's A:N cells to be empty. Advance the in-memory insertion pointer only after exact verification.

When reconciliation finds exactly one existing Main plus one Premier row, read their exact A:R cells and require O:R formulas in both. When it finds exactly one cabin row, accept it only with the matching partial marker described above and require O:R formulas in that row. If formulas are missing, use one fenced batch to repair only the existing fare rows and checkpoint `Listo`; clear M for a full pair or preserve the verified partial marker for one cabin. Read back A:R and never checkpoint a formula-less fare row.

## Failure Commit

For a terminal failure, recheck fence/lease and queue ownership, then use one fenced batch to update only queue G=`Error` and M with the structured error detail. Preserve H:J:K:L and every unrelated cell.

## Unknown Commit Matrix

After any timeout or ambiguous write response, read the exact intended destination rows, queue row, and cursor before retrying:

- Every intended contiguous fare row, queue checkpoint/partial marker, and cursor match: accept the commit.
- No intended fare row, queue checkpoint, or cursor changed: retry the identical batch once after rechecking fence ownership and the exact empty destination A:N range.
- Any unintended subset changed, an internal blank was introduced, cursor differs, values/marker differ, or duplicate identity appears: do not replay. Stop new dispatch globally, reconcile the shared state, report an integrity error, and leave the task unarchived.

## Final Verification

Read every changed queue row and every compact A:R write range. Require either one Main plus one Premier for full success or exactly the validated cabin row plus matching partial marker for partial success. Require formulas in every fare row, no internal A:N blanks before B4, no owned `En curso`, no writes outside the intended grids, and no duplicate identity introduced by this run.

If an internal A:N blank is found before B4, do not finish or release the fence. Preserve populated-row order, compact the complete A:R rows upward under the owned fence, clear only the vacated trailing A:N cells, update B4 atomically, and repeat the full readback. A run can finish only after the compacted range and cursor reconcile with no internal gap.
