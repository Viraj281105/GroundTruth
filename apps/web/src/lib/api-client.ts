/**
 * A typed client for the GroundTruth API, generated from its OpenAPI schema.
 *
 * Every path, parameter, request body and response here is checked against
 * `./generated/schema.d.ts`, so a call that does not match the backend fails
 * `npm run typecheck` instead of failing at runtime. It is the transport for the
 * stored-run (`/runs`) and job (`/jobs`) endpoints; wiring pages to it is #40.
 *
 * It is ONLY transport. It has no fixture or demo fallback of any kind: a network
 * failure rejects, and an error response comes back as `error`. Anything that
 * may show demo data must keep going through `./api.ts`, where that is gated by
 * `isDemoMode()` and checked by `npm run check:fixture-fallback`.
 */

import createClient from "openapi-fetch";

import { API_BASE_URL } from "./api";
import type { components, paths } from "./generated/schema";
import { withSessionWatch } from "./session-events";

/** Every schema the API declares, by name: `Schemas["RunDetail"]`, `Schemas["JobView"]`. */
export type Schemas = components["schemas"];

export type { components, paths };

export interface ApiClientOptions {
  /** Defaults to `API_BASE_URL` (`NEXT_PUBLIC_API_URL`, or localhost:8000). */
  baseUrl?: string;
  /** Defaults to the global `fetch`. Tests pass a stand-in. */
  fetch?: typeof globalThis.fetch;
}

/** A client bound to one API base URL. */
export function createApiClient(options: ApiClientOptions = {}) {
  return createClient<paths>({
    baseUrl: options.baseUrl ?? API_BASE_URL,
    // Cookie sessions: send the HttpOnly session cookie. A 401 announces an expired session.
    credentials: "include",
    fetch: options.fetch ?? withSessionWatch((...a) => globalThis.fetch(...a)),
  });
}

export type ApiClient = ReturnType<typeof createApiClient>;
