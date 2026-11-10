// The run flow after #49: a lost API mid-run is said plainly and keeps the run's id, and the
// optional stricter minimum can only be a whole number of at least 2.
import { describe, expect, it } from "vitest";
import { initialState, reduce } from "../src/features/run/machine";
import { parseMinDonors } from "../src/features/run/RunFlow";
import type { JobView } from "../src/lib/jobs";

const job = (over: Record<string, unknown> = {}) =>
  ({ run_id: "run_1", case_id: "c", terminal: false, result_state: "running", stages: [], error: null, failure_reason: null, ...over }) as unknown as JobView;

describe("lost contact during a run", () => {
  it("ends in its own outcome, keeps the run id and never claims nothing ran", () => {
    let s = reduce(initialState, { type: "start" });
    s = reduce(s, { type: "submitted", job: job() });
    s = reduce(s, { type: "lostContact", reason: "The API could not be reached." });
    expect(s.step).toBe("results");
    expect(s.outcome?.kind).toBe("lostContact");
    expect(s.outcome?.title).toBe("Lost contact with the analysis service");
    expect(s.runId).toBe("run_1");
    expect(`${s.outcome?.reason} ${s.outcome?.next}`).not.toMatch(/no analysis was run/i);
  });

  it("falls back to an honest sentence when the error has no usable text", () => {
    const s = reduce(reduce(initialState, { type: "submitted", job: job() }), { type: "lostContact" });
    expect(s.outcome?.reason).toMatch(/may still finish/);
  });
});

describe("the stricter minimum", () => {
  it("is optional", () => {
    expect(parseMinDonors("")).toBeUndefined();
    expect(parseMinDonors("  ")).toBeUndefined();
  });

  it("takes a whole number of at least 2", () => {
    expect(parseMinDonors("40")).toBe(40);
    expect(parseMinDonors("500")).toBe(500);
  });

  it("refuses anything else instead of guessing", () => {
    for (const bad of ["1", "0", "-3", "2.5", "abc"]) expect(parseMinDonors(bad)).toBeNull();
  });
});
