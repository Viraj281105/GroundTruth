/**
 * Issue #17: the API types are generated, and the typed client is plain transport.
 *
 * The `expectTypeOf` assertions are checked by `npm run typecheck` (tsc), which is
 * where a hand-written backend shape sneaking back into types.ts would fail. The
 * runtime tests use a stand-in `fetch`, so no server is needed.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, expectTypeOf, it } from 'vitest';

import { createApiClient } from '../src/lib/api-client';
import type { components } from '../src/lib/generated/schema';
import type * as T from '../src/lib/types';

type Schemas = components['schemas'];

describe('types.ts re-exports the generated types under the old names', () => {
  it('each backend shape is the generated one, not a hand-written copy', () => {
    expectTypeOf<T.Confidence>().toEqualTypeOf<Schemas['Confidence']>();
    expectTypeOf<T.Provenance>().toEqualTypeOf<Schemas['Provenance']>();
    expectTypeOf<T.Evidence>().toEqualTypeOf<Schemas['Evidence']>();
    expectTypeOf<T.VerdictLabel>().toEqualTypeOf<Schemas['VerdictLabel']>();
    expectTypeOf<T.VerificationVerdict>().toEqualTypeOf<Schemas['VerificationVerdict']>();
    expectTypeOf<T.EvidenceBundle>().toEqualTypeOf<Schemas['EvidenceBundle']>();
    expectTypeOf<T.CaseSummary>().toEqualTypeOf<Schemas['CaseSummary']>();
    expectTypeOf<T.CaseDetail>().toEqualTypeOf<Schemas['CaseDetail']>();
    expectTypeOf<T.VerificationRequest>().toEqualTypeOf<Schemas['VerificationRequest']>();
    expectTypeOf<T.HealthResponse>().toEqualTypeOf<Schemas['HealthResponse']>();
    expectTypeOf<T.VerificationResponse>().toEqualTypeOf<Schemas['VerificationResponse']>();
  });

  it('fields the API always sends are typed as always present', () => {
    expectTypeOf<T.Evidence['qualifiers']>().toEqualTypeOf<{ [key: string]: unknown }>();
    expectTypeOf<T.VerificationResponse['spec_hash']>().toEqualTypeOf<string>();
    expectTypeOf<T.VerificationResponse['run_id']>().toEqualTypeOf<string>();
    expectTypeOf<T.HealthResponse['engine_capabilities']>().toEqualTypeOf<{
      [key: string]: boolean;
    }>();
  });

  it('request fields with defaults stay optional', () => {
    expectTypeOf<{ case_id: string }>().toMatchTypeOf<Schemas['SubmitJobRequest']>();
    expectTypeOf<Record<string, never>>().toMatchTypeOf<T.VerificationRequest>();
  });

  it('records the known mismatches rather than hiding them', () => {
    // The backend types Confidence.kind as a free string; the UI's ConfidenceKind
    // is narrower. See docs/architecture/frontend.md.
    expectTypeOf<T.Confidence['kind']>().toEqualTypeOf<string>();
    expectTypeOf<T.ConfidenceKind>().toMatchTypeOf<T.Confidence['kind']>();
    // Narrowed on the backend in #17, so these now match what the UI expected.
    expectTypeOf<T.VerificationResponse['verdict_label']>().toEqualTypeOf<T.VerdictLabel>();
    expectTypeOf<T.VerificationResponse['data_mode']>().toEqualTypeOf<'simulated' | 'observed'>();
  });

  it('the refusal body the demo fixtures use is the generated one', () => {
    type RefusalErrorBody = import('../src/lib/fixtures/generated').RefusalErrorBody;
    expectTypeOf<RefusalErrorBody>().toEqualTypeOf<Schemas['EngineFailureBody']>();
  });
});

/** A stand-in for fetch that records requests and answers with a fixed response. */
function stub(status: number, body: unknown) {
  const requests: Request[] = [];
  const fetchStub = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    requests.push(request);
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  return { requests, fetch: fetchStub as typeof globalThis.fetch };
}

describe('the typed client', () => {
  it('builds the path and query from typed parameters', async () => {
    const { requests, fetch } = stub(200, { run_id: 'run_0000000000000001' });
    const client = createApiClient({ baseUrl: 'http://api.test', fetch });

    const { data, error } = await client.GET('/runs/{run_id}', {
      params: { path: { run_id: 'run_0000000000000001' }, query: { include_bundle: false } },
    });

    expect(error).toBeUndefined();
    expect(data?.run_id).toBe('run_0000000000000001');
    expect(requests).toHaveLength(1);
    expect(requests[0].method).toBe('GET');
    expect(requests[0].url).toBe('http://api.test/runs/run_0000000000000001?include_bundle=false');
    expectTypeOf(data).toEqualTypeOf<Schemas['RunDetail'] | undefined>();
  });

  it('sends a typed JSON body', async () => {
    const { requests, fetch } = stub(202, { run_id: 'run_0000000000000002' });
    const client = createApiClient({ baseUrl: 'http://api.test', fetch });

    await client.POST('/jobs', { body: { case_id: 'kariba-redd', min_donors: 12 } });

    expect(requests[0].method).toBe('POST');
    expect(requests[0].url).toBe('http://api.test/jobs');
    expect(await requests[0].json()).toEqual({ case_id: 'kariba-redd', min_donors: 12 });
  });

  it('returns an error response as `error`, not as data', async () => {
    const detail = { code: 'run_not_found', message: "No run 'run_x'.", hint: null };
    const { fetch } = stub(404, { detail });
    const client = createApiClient({ baseUrl: 'http://api.test', fetch });

    const { data, error, response } = await client.GET('/runs/{run_id}', {
      params: { path: { run_id: 'run_x' } },
    });

    expect(data).toBeUndefined();
    expect(response.status).toBe(404);
    expect(error).toEqual({ detail });
  });

  it('rejects when the network fails, with no fallback of any kind', async () => {
    const failing = (async () => {
      throw new TypeError('fetch failed');
    }) as typeof globalThis.fetch;
    const client = createApiClient({ baseUrl: 'http://api.test', fetch: failing });

    await expect(client.GET('/health')).rejects.toThrow('fetch failed');
  });

  it('cannot serve demo data: it never touches fixtures or demo mode', () => {
    const source = readFileSync(join(__dirname, '..', 'src', 'lib', 'api-client.ts'), 'utf8');
    const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
    expect(code).not.toMatch(/MOCK_|fixtures|isDemoMode|isDemo\b/);
  });

  it('rejects calls that do not match the API, at compile time', () => {
    const client = createApiClient({ baseUrl: 'http://api.test', fetch: stub(200, {}).fetch });
    // These are never executed; tsc checks them.
    const neverRun = () => {
      // @ts-expect-error a path the API does not have
      void client.GET('/not-a-path');
      // @ts-expect-error a job submission needs a case_id
      void client.POST('/jobs', { body: { min_donors: 12 } });
      // (An extra body field such as true_effect is not caught here: the body passes
      // through a generic, which skips TypeScript's excess-property check. The API
      // rejects it with 422 at runtime; see tests/test_job_api.py.)
      // @ts-expect-error the run id is required
      void client.GET('/runs/{run_id}', { params: { path: {} } });
    };
    expect(neverRun).toBeTypeOf('function');
  });
});
