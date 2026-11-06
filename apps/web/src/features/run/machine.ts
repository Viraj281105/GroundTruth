/** Pure state machine for the run flow: Configure -> Run -> Results. */
import type { JobView } from "../../lib/jobs";
import { runCopy } from "./copy";

export type Step = "configure" | "run" | "results";
export type OutcomeKind = "refused" | "failed" | "cancelled" | "unreachable";

export interface Outcome {
  kind: OutcomeKind;
  title: string;
  reason: string;
  next: string;
}

export interface RunState {
  step: Step;
  submitting: boolean;
  cancelling: boolean;
  runId: string | null;
  job: JobView | null;
  /** Set when the run ended without a measured result. */
  outcome: Outcome | null;
}

export type RunEvent =
  | { type: "start" }
  | { type: "submitted"; job: JobView }
  | { type: "progress"; job: JobView }
  | { type: "done"; job: JobView }
  | { type: "submitFailed"; reason?: string; unreachable?: boolean }
  | { type: "cancel" }
  | { type: "reset" };

export const initialState: RunState = {
  step: "configure",
  submitting: false,
  cancelling: false,
  runId: null,
  job: null,
  outcome: null,
};

export const STEP_ORDER: readonly Step[] = ["configure", "run", "results"];

/** Plain-language reason text. Never a stack, never raw JSON. */
function cleanReason(text: string | null | undefined, fallback: string): string {
  const t = (text ?? "").trim();
  if (!t || t.startsWith("{") || t.startsWith("[") || /Traceback|\n\s+at /.test(t)) return fallback;
  return t;
}

export function outcomeFor(kind: OutcomeKind, reason?: string | null, remediation?: string | null): Outcome {
  const c = runCopy.outcomes[kind];
  return {
    kind,
    title: c.title,
    reason: cleanReason(reason, c.fallback),
    next: cleanReason(remediation, c.next),
  };
}

/** Map a finished job to either a measured result (null) or an explained outcome. */
export function outcomeFromJob(job: JobView): Outcome | null {
  switch (job.result_state) {
    case "measured":
      return null;
    case "refused":
      return outcomeFor("refused", job.error?.message ?? job.failure_reason, job.error?.remediation);
    case "cancelled":
      return outcomeFor("cancelled", null, null);
    default:
      return outcomeFor("failed", job.error?.message ?? job.failure_reason, job.error?.remediation);
  }
}

export function reduce(state: RunState, event: RunEvent): RunState {
  switch (event.type) {
    case "start":
      return state.step === "configure" && !state.submitting ? { ...state, submitting: true, outcome: null } : state;
    case "submitted":
      return event.job.terminal
        ? reduce({ ...state, runId: event.job.run_id, submitting: false }, { type: "done", job: event.job })
        : { ...state, step: "run", submitting: false, runId: event.job.run_id, job: event.job };
    case "progress":
      return state.step === "run" ? { ...state, job: event.job } : state;
    case "done":
      return {
        ...state,
        step: "results",
        submitting: false,
        cancelling: false,
        runId: event.job.run_id,
        job: event.job,
        outcome: outcomeFromJob(event.job),
      };
    case "submitFailed":
      return {
        ...initialState,
        step: "results",
        outcome: outcomeFor(event.unreachable ? "unreachable" : "failed", event.reason),
      };
    case "cancel":
      return state.step === "run" ? { ...state, cancelling: true } : state;
    case "reset":
      return initialState;
  }
}

/** Index of the active step, for the stepper. */
export function stepIndex(step: Step): number {
  return STEP_ORDER.indexOf(step);
}

export function stageLabel(name: string, apiLabel?: string): string {
  return runCopy.stageLabels[name] ?? (apiLabel || name);
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
