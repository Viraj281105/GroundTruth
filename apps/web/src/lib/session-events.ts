/** A tiny event bus so any API call can report "the session expired" without importing React. */
export const SESSION_EXPIRED_EVENT = 'gt:session-expired';

export function notifySessionExpired(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

/** Wrap fetch so a 401 from a non-auth endpoint announces an expired session. */
export function withSessionWatch(inner: typeof globalThis.fetch): typeof globalThis.fetch {
  return async (input, init) => {
    const res = await inner(input, init);
    if (res.status === 401) {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!/\/auth\/(login|register|me|logout|change-password)/.test(url)) notifySessionExpired();
    }
    return res;
  };
}
