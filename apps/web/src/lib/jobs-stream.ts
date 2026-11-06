/**
 * Live job progress over Server-Sent Events, with a polling fallback.
 *
 * `GET {API}/jobs/{id}/events` sends `progress` and `done` events carrying the
 * JobView JSON, and `error` / `timeout` events that end the stream. When the
 * stream fails or times out, this falls back to polling the status endpoint
 * every 1.5 s. Reconnecting the stream is deliberately not attempted.
 * Everything is injectable so it can run without a browser.
 */

import { API_BASE_URL } from "./api";
import { createJobsApi, type JobView } from "./jobs";

export interface EventSourceLike {
  addEventListener(type: string, listener: (event: { data?: string }) => void): void;
  close(): void;
}

export interface WatchHandlers {
  onProgress(view: JobView): void;
  onDone(view: JobView): void;
  onError(err: unknown): void;
}

export interface WatchStreamOptions {
  baseUrl?: string;
  fetchStatus?: (runId: string) => Promise<JobView>;
  eventSourceFactory?: (url: string) => EventSourceLike;
  pollMs?: number;
}

export const STREAM_POLL_MS = 1500;

function parseView(data: string | undefined): JobView | null {
  if (!data) return null;
  try {
    const value: unknown = JSON.parse(data);
    return value && typeof value === "object" && "run_id" in value ? (value as JobView) : null;
  } catch {
    return null;
  }
}

/** Watch one run. Returns an unsubscribe function that stops everything. */
export function watchJob(runId: string, handlers: WatchHandlers, opts: WatchStreamOptions = {}): () => void {
  const baseUrl = opts.baseUrl ?? API_BASE_URL;
  const pollMs = opts.pollMs ?? STREAM_POLL_MS;
  const fetchStatus = opts.fetchStatus ?? ((id: string) => createJobsApi({ baseUrl }).status(id));
  const factory =
    opts.eventSourceFactory ??
    (typeof EventSource !== "undefined" ? (url: string) => new EventSource(url) as EventSourceLike : null);

  let stopped = false;
  let source: EventSourceLike | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let polling = false;

  function stop() {
    stopped = true;
    if (timer) clearTimeout(timer);
    timer = null;
    source?.close();
    source = null;
  }

  const finish = (view: JobView) => {
    if (stopped) return;
    stop();
    handlers.onDone(view);
  };

  const emit = (view: JobView) => {
    if (stopped) return;
    if (view.terminal) finish(view);
    else handlers.onProgress(view);
  };

  const poll = async () => {
    timer = null;
    if (stopped) return;
    try {
      const view = await fetchStatus(runId);
      if (stopped) return;
      emit(view);
    } catch (err) {
      if (stopped) return;
      stop();
      handlers.onError(err);
      return;
    }
    if (!stopped) timer = setTimeout(poll, pollMs);
  };

  const startPolling = () => {
    if (polling || stopped) return;
    polling = true;
    source?.close();
    source = null;
    timer = setTimeout(poll, pollMs);
  };

  if (!factory) {
    startPolling();
    return stop;
  }

  try {
    source = factory(`${baseUrl}/jobs/${encodeURIComponent(runId)}/events`);
  } catch {
    startPolling();
    return stop;
  }
  source.addEventListener("progress", (e) => {
    const view = parseView(e.data);
    if (view) emit(view);
  });
  source.addEventListener("done", (e) => {
    const view = parseView(e.data);
    if (view) finish(view);
    else startPolling();
  });
  source.addEventListener("error", () => startPolling());
  source.addEventListener("timeout", () => startPolling());
  return stop;
}
