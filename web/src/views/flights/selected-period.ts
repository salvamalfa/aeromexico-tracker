import { currentPeriodId } from "../../state/period";
import type { QuarterRecord } from "../../types/domain";
import { state } from "./state";

// An unavailable selection is an empty calendar window, never the last
// successful index. Financial, passenger and route coverage stay independent.
export function selectedFlightQuarter(): QuarterRecord {
  const id = currentPeriodId() ?? state.quarters[state.periodIndex]?.period_id;
  if (!id) throw new Error("No hay trimestre seleccionado.");
  const record = state.byPeriod.get(id) ?? state.quarters.find(row => row.period_id === id);
  if (record) return record;
  const year = Number(id.slice(0,4)); const month = (Number(id.slice(-1)) - 1) * 3;
  return { period_id: id, period_label: `${id.slice(-1)}T${id.slice(2,4)}`, metrics: {
    passengers: { value: null, period_start: new Date(Date.UTC(year,month,1)).toISOString().slice(0,10),
      period_end: new Date(Date.UTC(year,month+3,0)).toISOString().slice(0,10) },
    asm_miles: { value: null }, rpm_miles: { value: null }, load_factor: { value: null },
  } };
}
