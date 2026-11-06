import { describe, expect, it, vi } from "vitest";
import { watchJob, type EventSourceLike } from "../src/lib/jobs-stream";
import type { JobView } from "../src/lib/jobs";

const view = (over: Partial<JobView> = {}) =>
  ({ run_id: "r1", case_id: "c", terminal: false, stages: [], ...over }) as unknown as JobView;

function fakeSource() {
  const listeners: Record<string, (e: { data?: string }) => void> = {};
  const src: EventSourceLike & { closed: boolean; emit(t: string, d?: unknown): void } = {
    closed: false,
    addEventListener: (t, l) => void (listeners[t] = l),
    close() {
      src.closed = true;
    },
    emit: (t, d) => listeners[t]?.({ data: d === undefined ? undefined : JSON.stringify(d) }),
  };
  return src;
}

const handlers = () => ({ onProgress: vi.fn(), onDone: vi.fn(), onError: vi.fn() });

describe("watchJob", () => {
  it("maps progress and done events and closes the stream", () => {
    const src = fakeSource();
    const h = handlers();
    let url = "";
    watchJob("r1", h, {
      baseUrl: "http://x",
      eventSourceFactory: (u) => {
        url = u;
        return src;
      },
    });
    expect(url).toBe("http://x/jobs/r1/events");
    src.emit("progress", view({ stage: "fit" }));
    expect(h.onProgress).toHaveBeenCalledTimes(1);
    src.emit("done", view({ terminal: true }));
    expect(h.onDone).toHaveBeenCalledTimes(1);
    expect(src.closed).toBe(true);
  });

  it("falls back to polling on error and finishes on a terminal status", async () => {
    vi.useFakeTimers();
    const src = fakeSource();
    const h = handlers();
    const fetchStatus = vi
      .fn()
      .mockResolvedValueOnce(view())
      .mockResolvedValueOnce(view({ terminal: true }));
    watchJob("r1", h, { eventSourceFactory: () => src, fetchStatus });
    src.emit("error");
    expect(src.closed).toBe(true);
    await vi.advanceTimersByTimeAsync(1500);
    expect(h.onProgress).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1500);
    expect(h.onDone).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchStatus).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("falls back on a timeout event and reports polling failures", async () => {
    vi.useFakeTimers();
    const src = fakeSource();
    const h = handlers();
    const boom = new Error("down");
    watchJob("r1", h, { eventSourceFactory: () => src, fetchStatus: () => Promise.reject(boom) });
    src.emit("timeout");
    await vi.advanceTimersByTimeAsync(1500);
    expect(h.onError).toHaveBeenCalledWith(boom);
    vi.useRealTimers();
  });

  it("unsubscribe stops the stream and the polling", async () => {
    vi.useFakeTimers();
    const src = fakeSource();
    const h = handlers();
    const fetchStatus = vi.fn().mockResolvedValue(view());
    const stop = watchJob("r1", h, { eventSourceFactory: () => src, fetchStatus });
    src.emit("error");
    stop();
    await vi.advanceTimersByTimeAsync(6000);
    expect(fetchStatus).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
