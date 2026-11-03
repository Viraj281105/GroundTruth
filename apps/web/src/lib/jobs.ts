/**
 * Running an analysis through the job queue, from the browser (issue #40).
 *
 * The page submits a job (`POST /jobs`), polls its status (`GET /jobs/{id}`)
 * until the API says it is `terminal`, and then reads the stored result
 * (`GET /runs/{id}`). Everything shown while it runs is what the API reported:
 * there is no simulated progress and no percentage, because none can be known.
 *
 * Like `./api-client.ts`, this is transport only. It never returns fixture
 * data: a network failure throws `ApiUnreachableError`, and the one place
 * allowed to substitute a fixture for it is the page, through the
 * `isDemoMode()`-gated helpers in `./api.ts`.
 */

import { API_BASE_URL, ApiUnreachableError, type RefusalInfo } from "./api";
import { createApiClient, type ApiClientOptions, type Schemas } from "./api-client";
import type { LoadingStage } from "../components/ui/States";
import type { VerificationResponse } from "./types";

export type JobView = Schemas["JobView"];
export type JobSubmission = Schemas["JobSubmission"];
export type RunDetail = Schemas["RunDetail"];
export type StageView = Schemas["StageView"];
export type SubmitJobRequest = Schemas["SubmitJobRequest"];

/** What the page renders for a measured run, whether it came from `/verify` or `/runs`. */
export type DisplayedResult = Pick<
  VerificationResponse,
  "run_id" | "spec_hash" | "data_mode" | "bundle" | "report_markdown" | "report_generator"
>;

/** Any failure, reduced to what the error state shows: a code, a message, a remedy. */
export interface ApiFailure {
  /** The API's error code, or `HTTP <status>` when the body carried none. */
  code: string | null;
  message: string;
  remediation: string | null;
  /** HTTP status, when the API answered at all. */
  status: number | null;
}

/** The API answered with an error status. */
export class ApiRequestError extends Error {
  constructor(
    public readonly status: number | null,
    public readonly code: string | null,
    message: string,
    public readonly remediation: string | null,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

/** Polling saw no answer for long enough that the page stops and says so. */
export class LostContactError extends Error {
  constructor(
    public readonly runId: string,
    public readonly lastError: unknown,
  ) {
    super(`Lost contact with the API while watching run ${runId}.`);
    this.name = "LostContactError";
  }
}

const str = (value: unknown): string | null => (typeof value === "string" && value ? value : null);

/**
 * Normalise an error body. The API sends four shapes: `{detail: {code, message,
 * hint}}` (ApiErrorBody), `{detail: {code, message, remediation, ...}}` from
 * `/verify` (EngineFailureBody), `{detail: "text"}` (MessageErrorBody), and
 * FastAPI's `{detail: [{loc, msg}]}` validation errors. A proxy in front of a
 * deployed API may send anything else, including HTML.
 */
export function describeApiError(status: number, body: unknown): ApiFailure {
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;
  const fallbackCode = `HTTP ${status}`;

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    return {
      code: str(d.code) ?? fallbackCode,
      message: str(d.message) ?? `The API answered HTTP ${status}.`,
      remediation: str(d.hint) ?? str(d.remediation),
      status,
    };
  }
  if (typeof detail === "string" && detail) {
    return { code: fallbackCode, message: detail, remediation: null, status };
  }
  if (Array.isArray(detail)) {
    const problems = detail
      .map((item) => {
        const entry = item as { loc?: unknown[]; msg?: unknown };
        const where = Array.isArray(entry.loc) ? entry.loc.join(".") : "";
        return [where, str(entry.msg)].filter(Boolean).join(": ");
      })
      .filter(Boolean);
    return {
      code: fallbackCode,
      message: `The API rejected the request: ${problems.join("; ") || "invalid input"}.`,
      remediation: null,
      status,
    };
  }
  return {
    code: fallbackCode,
    message: `The API answered HTTP ${status} with no error detail.`,
    remediation: null,
    status,
  };
}

/** What to check when the browser could not reach the API at all. */
export function unreachableRemediation(apiBaseUrl: string, origin?: string): string {
  // A cross-origin call the API refuses fails in the browser exactly like a dead
  // server, so the CORS setting is named here rather than left to guesswork.
  return (
    `Check that the API is running at ${apiBaseUrl} and reachable from this browser. ` +
    `If it is, add this site's origin${origin ? ` (${origin})` : ""} to the API's ` +
    "CORS_ALLOWED_ORIGINS: a browser reports a refused cross-origin call as unreachable."
  );
}

/** Reduce anything thrown by the calls below to an `ApiFailure`. */
export function failureFrom(err: unknown, origin?: string): ApiFailure {
  if (err instanceof ApiRequestError) {
    return { code: err.code, message: err.message, remediation: err.remediation, status: err.status };
  }
  if (err instanceof ApiUnreachableError) {
    return {
      code: "api_unreachable",
      message: `${err.message} No verification was executed.`,
      remediation: unreachableRemediation(err.apiBaseUrl, origin),
      status: null,
    };
  }
  return {
    code: null,
    message: err instanceof Error ? err.message : "An unexpected error occurred.",
    remediation: null,
    status: null,
  };
}

const isAbort = (err: unknown): boolean =>
  typeof err === "object" && err !== null && (err as { name?: unknown }).name === "AbortError";

const abortError = (): Error => new DOMException("Watching stopped.", "AbortError");

/** Bind the job and run endpoints to one API base URL. */
export function createJobsApi(options: ApiClientOptions = {}) {
  const baseUrl = options.baseUrl ?? API_BASE_URL;
  const client = createApiClient(options);

  async function send<T>(
    call: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  ): Promise<T> {
    let result: { data?: T; error?: unknown; response: Response };
    try {
      result = await call();
    } catch (err) {
      if (isAbort(err)) throw err;
      if (err instanceof SyntaxError) {
        throw new ApiRequestError(null, null, "The API sent a response that is not valid JSON.", null);
      }
      throw new ApiUnreachableError(baseUrl, err);
    }
    if (result.response.ok && result.data !== undefined) return result.data;
    const failure = describeApiError(result.response.status, result.error);
    throw new ApiRequestError(failure.status, failure.code, failure.message, failure.remediation);
  }

  return {
    baseUrl,
    /** Queue an analysis. A `200` (cached or deduplicated) and a `202` both return a submission. */
    submit: (body: SubmitJobRequest) => send(() => client.POST("/jobs", { body })),
    status: (runId: string, signal?: AbortSignal) =>
      send(() => client.GET("/jobs/{run_id}", { params: { path: { run_id: runId } }, signal })),
    cancel: (runId: string) =>
      send(() => client.POST("/jobs/{run_id}/cancel", { params: { path: { run_id: runId } } })),
    /** The stored run, with the deterministic report when asked for. */
    result: (runId: string, includeReport: boolean) =>
      send(() =>
        client.GET("/runs/{run_id}", {
          params: { path: { run_id: runId }, query: { include_report: includeReport } },
        }),
      ),
  };
}

export type JobsApi = ReturnType<typeof createJobsApi>;

/** A failure worth retrying while polling: the network, or the server side of it. */
function isTransient(err: unknown): boolean {
  if (err instanceof ApiUnreachableError) return true;
  if (err instanceof ApiRequestError) {
    // Not configured is a deployment fact, not a blip; waiting will not change it.
    if (err.code === "store_not_configured") return false;
    return err.status !== null && err.status >= 500;
  }
  return false;
}

export interface WatchOptions {
  /** Called with every status the API returns, the terminal one included. */
  onUpdate: (job: JobView) => void;
  signal?: AbortSignal;
  /** A status for a different case is an error, not something to display. */
  caseId?: string;
  intervalMs?: number;
  /** Waits after consecutive transient failures; the last value repeats. */
  backoffMs?: readonly number[];
  /** With no answer for this long, give up with `LostContactError`. */
  lostContactAfterMs?: number;
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  now?: () => number;
}

export const POLL_INTERVAL_MS = 1000;
export const POLL_BACKOFF_MS: readonly number[] = [1000, 2000, 4000, 8000, 10000];
export const LOST_CONTACT_AFTER_MS = 30000;

export function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Poll a job until the API says it is terminal, and return that final status.
 *
 * About once a second while it answers. A dropped connection or a 5xx backs
 * off (1, 2, 4, 8, then 10 s) and, after 30 s with no answer, ends in
 * `LostContactError`, so the page can offer to resume instead of spinning
 * forever. Any other error (an unknown run, a store that is not configured)
 * ends the watch at once. Aborting the signal ends it with an `AbortError`.
 */
export async function watchJob(api: JobsApi, runId: string, options: WatchOptions): Promise<JobView> {
  const {
    onUpdate,
    signal,
    caseId,
    intervalMs = POLL_INTERVAL_MS,
    backoffMs = POLL_BACKOFF_MS,
    lostContactAfterMs = LOST_CONTACT_AFTER_MS,
    sleep = abortableSleep,
    now = Date.now,
  } = options;

  let lastContact = now();
  let failures = 0;
  for (;;) {
    let job: JobView;
    try {
      job = await api.status(runId, signal);
    } catch (err) {
      if (signal?.aborted || isAbort(err)) throw abortError();
      if (!isTransient(err)) throw err;
      failures += 1;
      if (now() - lastContact >= lostContactAfterMs) throw new LostContactError(runId, err);
      await sleep(backoffMs[Math.min(failures - 1, backoffMs.length - 1)], signal);
      continue;
    }
    if (signal?.aborted) throw abortError();
    failures = 0;
    lastContact = now();
    if (caseId !== undefined && job.case_id !== caseId) {
      throw new ApiRequestError(
        null,
        "run_case_mismatch",
        `Run ${runId} belongs to case ${job.case_id}, not ${caseId}.`,
        "Open the run from its own case page, or remove ?run= from the address.",
      );
    }
    onUpdate(job);
    if (job.terminal) return job;
    await sleep(intervalMs, signal);
  }
}

/** A refused job as the refusal state shows it. Uses the engine's own words. */
export function refusalFromJob(job: JobView): RefusalInfo {
  const error = job.error;
  return {
    message: error?.message ?? "The engine refused this analysis and recorded no reason.",
    code: error?.code,
    stage: error?.stage,
    remediation: error?.remediation ?? null,
    runId: job.run_id,
    detail: error?.detail,
  };
}

/** A failed job as the error state shows it. */
export function failureFromJob(job: JobView): ApiFailure {
  return {
    code: job.error?.code ?? null,
    message:
      job.error?.message ??
      job.failure_reason ??
      `Run ${job.run_id} failed and recorded no reason.`,
    remediation: job.error?.remediation ?? null,
    status: null,
  };
}

/** A stored run in the shape the results section renders, or null when it has no bundle. */
export function displayedResultFromRun(run: RunDetail): DisplayedResult | null {
  if (!run.bundle) return null;
  return {
    run_id: run.run_id,
    spec_hash: run.spec_hash,
    // Unknown is never promoted to observed: only an explicit false is (R7).
    data_mode: run.is_simulated === false ? "observed" : "simulated",
    bundle: run.bundle,
    report_markdown: run.report_markdown,
    report_generator: run.report_generator,
  };
}

function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** The stages the API observed, in the loading state's shape. Nothing is inferred. */
export function loadingStagesFromJob(job: JobView): LoadingStage[] {
  return job.stages.map((stage, index) => {
    const label = `${index + 1}. ${stage.label.toUpperCase()}`;
    switch (stage.state) {
      case "done":
        return {
          id: stage.name,
          label,
          state: "done",
          desc: stage.duration_ms !== null ? `Done in ${formatMs(stage.duration_ms)}` : "Done",
        };
      case "active":
        return {
          id: stage.name,
          label,
          state: "active",
          desc:
            stage.elapsed_ms !== null
              ? `In progress for ${formatMs(stage.elapsed_ms)}`
              : "In progress",
        };
      case "failed":
        return { id: stage.name, label, state: "failed", desc: "Stopped here" };
      case "skipped":
        return { id: stage.name, label, state: "pending", desc: "Not reached" };
      case "unknown":
        return { id: stage.name, label, state: "pending", desc: "Not recorded for this job" };
      default:
        return { id: stage.name, label, state: "pending", desc: "Not started yet" };
    }
  });
}
