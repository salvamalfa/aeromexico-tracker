// The one quarter/period-selection store shared by views/executive and
// views/flights — see web/README.md "Estado de trimestre compartido"
// (P6a). Owns the selected index and the single pair of click listeners
// on #period-prev/#period-next; each view subscribes here instead of
// keeping its own `periodIndex` and its own listeners on the same
// buttons (the design P4a/P4b/P5 had — see the "Mount order matters for
// parity" note this replaces).
//
// The canonical, ordered list of period_ids is set once, by whichever
// view loads first (views/executive/state.ts::loadExecutive, since the
// executive view always mounts and fetches eagerly — views/flights is
// mounted lazily, only once its tab is first opened, see
// views/flights/bootstrap.ts). A subscriber does not get an immediate
// callback on subscribe(); callers read currentPeriodId()/currentIndex()
// once at mount time to pick up whatever quarter is already selected
// (e.g. Vuelos opened after switching quarters on the reading tab), then
// rely on subscribe() for every later move — see mountExecutive/
// mountFlights.

import { $ } from "../views/flights/dom";

export type PeriodListener = (periodId: string) => void;

interface PeriodStore {
  periodIds: string[];
  index: number;
}

const store: PeriodStore = { periodIds: [], index: 0 };
const listeners: PeriodListener[] = [];
let wired = false;

export function initPeriods(periodIds: string[], defaultPeriodId?: string): void {
  store.periodIds = periodIds;
  store.index = Math.max(0, periodIds.findIndex((id) => id === defaultPeriodId));
}

export function currentPeriodId(): string | undefined {
  return store.periodIds[store.index];
}

export function currentIndex(): number {
  return store.index;
}

export function periodCount(): number {
  return store.periodIds.length;
}

export function subscribe(listener: PeriodListener): void {
  listeners.push(listener);
}

function movePeriod(offset: number): void {
  const next = store.index + offset;
  if (next < 0 || next >= store.periodIds.length) return;
  store.index = next;
  const periodId = store.periodIds[next]!;
  for (const listener of listeners) listener(periodId);
}

// Idempotent: the first mount to call this (views/executive/bootstrap.ts,
// always mounted first) wires the buttons; a later call (were
// views/flights ever to call it too) is a no-op, so the click never
// double-fires movePeriod().
export function wireStepper(): void {
  if (wired) return;
  wired = true;
  $("period-prev")!.addEventListener("click", () => movePeriod(-1));
  $("period-next")!.addEventListener("click", () => movePeriod(1));
}
