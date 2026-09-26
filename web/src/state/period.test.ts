import { describe, expect, it, vi } from "vitest";
import { currentIndex, currentPeriodId, initPeriods, periodCount, subscribe, wireStepper } from "./period";

// wireStepper()/subscribe() build module-level state (the buttons' click
// listeners, the subscriber list) that is meant to be set up exactly once
// per page load — so, unlike the rest of this repo's tests, this suite
// runs everything against one shared #period-prev/#period-next pair in a
// single test, instead of recreating it (and re-wiring) per case.
describe("state/period", () => {
  it("owns the selected index, the stepper buttons and every subscriber", () => {
    document.body.innerHTML = '<button id="period-prev"></button><button id="period-next"></button>';
    const prev = document.getElementById("period-prev") as HTMLButtonElement;
    const next = document.getElementById("period-next") as HTMLButtonElement;

    initPeriods(["2026Q1", "2026Q2", "2026Q3"], "2026Q2");
    expect(currentPeriodId()).toBe("2026Q2");
    expect(currentIndex()).toBe(1);
    expect(periodCount()).toBe(3);

    initPeriods(["2026Q1", "2026Q2"], "missing");
    expect(currentIndex()).toBe(0); // falls back to 0 when the default isn't in the list
    initPeriods(["2026Q1", "2026Q2", "2026Q3"], "2026Q2");

    wireStepper();
    wireStepper(); // idempotent: must never double-attach the click listeners

    const calls: string[] = [];
    subscribe((periodId) => calls.push(`a:${periodId}`));
    subscribe((periodId) => calls.push(`b:${periodId}`));

    next.click();
    expect(currentPeriodId()).toBe("2026Q3");
    // One click, one notification per subscriber, in subscription order —
    // the second wireStepper() call above did not attach a second listener.
    expect(calls).toEqual(["a:2026Q3", "b:2026Q3"]);

    next.click(); // already at the last quarter
    expect(currentPeriodId()).toBe("2026Q3");
    expect(calls).toHaveLength(2);

    prev.click();
    prev.click();
    prev.click(); // already at the first quarter
    expect(currentPeriodId()).toBe("2026Q1");
    expect(calls).toHaveLength(6);

    const late = vi.fn();
    subscribe(late);
    next.click();
    expect(late).toHaveBeenCalledExactlyOnceWith("2026Q2");
  });
});
