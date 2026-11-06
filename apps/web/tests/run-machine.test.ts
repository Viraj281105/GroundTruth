import { describe, expect, it } from "vitest";
import { formatElapsed, initialState, reduce, stageLabel, stepIndex } from "../src/features/run/machine";
import type { JobView } from "../src/lib/jobs";

const job = (over: Record<string, unknown> = {}) =>
  ({ run_id: "r1", case_id: "c", terminal: false, result_state: "running", stages: [], error: null, failure_reason: null, ...over }) as unknown as JobView;

describe("run machine", () => {
  it("moves configure -> run -> results for a measured run", () => {
    let s = reduce(initialState, { type: "start" });
    expect(s.submitting).toBe(true);
    s = reduce(s, { type: "submitted", job: job() });
    expect(s.step).toBe("run");
    s = reduce(s, { type: "progress", job: job({ stage: "fit" }) });
    expect(s.job?.stage).toBe("fit");
    s = reduce(s, { type: "done", job: job({ terminal: true, result_state: "measured" }) });
    expect(s.step).toBe("results");
    expect(s.outcome).toBeNull();
  });

  it("ignores a second start while submitting", () => {
    const s = reduce(initialState, { type: "start" });
    expect(reduce(s, { type: "start" })).toBe(s);
  });

  it("jumps to results when the submission is already terminal (cached)", () => {
    const s = reduce(initialState, { type: "submitted", job: job({ terminal: true, result_state: "measured" }) });
    expect(s.step).toBe("results");
  });

  it("explains a refusal with the engine's own words", () => {
    const s = reduce(initialState, {
      type: "done",
      job: job({ terminal: true, result_state: "refused", error: { message: "Too few comparison areas.", remediation: "Add more." } }),
    });
    expect(s.outcome).toMatchObject({ kind: "refused", reason: "Too few comparison areas.", next: "Add more." });
  });

  it("never surfaces raw JSON or stacks", () => {
    const s = reduce(initialState, {
      type: "done",
      job: job({ terminal: true, result_state: "failed", failure_reason: '{"detail":"x"}' }),
    });
    expect(s.outcome?.kind).toBe("failed");
    expect(s.outcome?.reason).not.toContain("{");
  });

  it("handles cancel, unreachable and reset", () => {
    const running = reduce(initialState, { type: "submitted", job: job() });
    expect(reduce(running, { type: "cancel" }).cancelling).toBe(true);
    const c = reduce(running, { type: "done", job: job({ terminal: true, result_state: "cancelled" }) });
    expect(c.outcome?.kind).toBe("cancelled");
    const u = reduce(initialState, { type: "submitFailed", unreachable: true });
    expect(u.outcome?.kind).toBe("unreachable");
    expect(reduce(u, { type: "reset" })).toEqual(initialState);
  });

  it("labels stages with a fallback to the API label then the raw name", () => {
    expect(stageLabel("fit")).toBe("Fit the comparison");
    expect(stageLabel("zzz", "Custom")).toBe("Custom");
    expect(stageLabel("zzz")).toBe("zzz");
    expect(stepIndex("results")).toBe(2);
    expect(formatElapsed(65000)).toBe("1:05");
  });
});
