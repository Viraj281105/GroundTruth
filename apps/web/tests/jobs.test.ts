import { describe, expect, it } from 'vitest';
import { ApiUnreachableError } from '../src/lib/api';
import {
  ApiRequestError,
  LostContactError,
  createJobsApi,
  describeApiError,
  displayedResultFromRun,
  failureFrom,
  failureFromJob,
  loadingStagesFromJob,
  refusalFromJob,
  watchJob,
  type JobView,
  type RunDetail,
} from '../src/lib/jobs';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import type { EvidenceBundle } from '../src/lib/types';

/**
 * The browser side of running an analysis through the job queue (issue #40).
 * The API is replaced by a fake `fetch`, so every request the page would send
 * is visible, and the clock and sleeps are fakes, so no test waits.
 */

const BASE = 'https://api.example.test';

function job(overrides: Partial<JobView> = {}): JobView {
  return {
    run_id: 'run-1',
    case_id: 'kariba-redd',
    status: 'queued',
    result_state: 'queued',
    terminal: false,
    engine_status: null,
    data_mode: 'simulated',
    is_simulated: true,
    notice: 'SIMULATED DATA',
    attempt: null,
    max_attempts: 3,
    cancel_requested: false,
    stage: null,
    stages: [],
    engine_metrics: {
      available: false,
      source: 'run_metrics',
      total_ms: null,
      stages: [],
      stopped_at: null,
      n_units_observed: null,
      n_donors_admitted: null,
      n_estimator_fits: null,
      note: '',
    },
    timeline: [],
    created_at: '2026-11-01T12:00:00Z',
    updated_at: null,
    last_heartbeat_at: null,
    lease_expires_at: null,
    retry_at: null,
    error: null,
    failure_reason: null,
    status_url: '/jobs/run-1',
    result_url: null,
    note: '',
    ...overrides,
  };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

interface Sent {
  method: string;
  url: string;
  body: string;
}

/** A fake API that answers from a queue of responses and records each request. */
function fakeApi(...answers: Array<Response | Error>) {
  const sent: Sent[] = [];
  const fetch = async (input: RequestInfo | URL): Promise<Response> => {
    const request = input as Request;
    sent.push({ method: request.method, url: request.url, body: await request.text() });
    const next = answers.shift();
    if (!next) throw new Error('fake API ran out of answers');
    if (next instanceof Error) throw next;
    return next;
  };
  return { api: createJobsApi({ baseUrl: BASE, fetch: fetch as typeof globalThis.fetch }), sent };
}

/** A clock that only moves when the code under test sleeps. */
function fakeTime() {
  let now = 0;
  const sleeps: number[] = [];
  return {
    sleeps,
    now: () => now,
    sleep: async (ms: number) => {
      sleeps.push(ms);
      now += ms;
    },
  };
}

describe('error bodies', () => {
  it('reads the API error shape: code, message and hint as remediation', () => {
    expect(
      describeApiError(503, {
        detail: {
          code: 'store_not_configured',
          message: 'No database is configured, so stored runs are not available.',
          hint: 'Set DATABASE_URL and run the migrations.',
        },
      }),
    ).toEqual({
      code: 'store_not_configured',
      message: 'No database is configured, so stored runs are not available.',
      remediation: 'Set DATABASE_URL and run the migrations.',
      status: 503,
    });
  });

  it("reads /verify's engine failure shape, whose remedy is called remediation", () => {
    const failure = describeApiError(500, {
      detail: { code: 'estimation_failed', message: 'did not converge', remediation: 'Retry.' },
    });
    expect(failure.code).toBe('estimation_failed');
    expect(failure.remediation).toBe('Retry.');
  });

  it('names the HTTP status when the body carries no code', () => {
    expect(describeApiError(404, { detail: "Unknown case 'x'" })).toMatchObject({
      code: 'HTTP 404',
      message: "Unknown case 'x'",
    });
    expect(describeApiError(502, '<html>Bad gateway</html>')).toMatchObject({
      code: 'HTTP 502',
      message: 'The API answered HTTP 502 with no error detail.',
    });
  });

  it('lists every field FastAPI rejected', () => {
    const failure = describeApiError(422, {
      detail: [
        { loc: ['body', 'min_donors'], msg: 'Input should be a valid integer', type: 'int_parsing' },
        { loc: ['body', 'case_id'], msg: 'Field required', type: 'missing' },
      ],
    });
    expect(failure.message).toContain('body.min_donors: Input should be a valid integer');
    expect(failure.message).toContain('body.case_id: Field required');
  });

  it('tells an unreachable API apart, and names CORS as a cause', () => {
    const failure = failureFrom(new ApiUnreachableError(BASE), 'https://app.example.test');
    expect(failure.code).toBe('api_unreachable');
    expect(failure.message).toContain('No verification was executed');
    expect(failure.remediation).toContain('CORS_ALLOWED_ORIGINS');
    expect(failure.remediation).toContain('https://app.example.test');
  });
});

describe('the jobs API client', () => {
  it('submits the run as the API expects, with no true_effect', async () => {
    const { api, sent } = fakeApi(
      json(202, { run_id: 'run-1', from_cache: false, deduplicated: false, status_url: '/jobs/run-1', job: job() }),
    );
    const submission = await api.submit({ case_id: 'kariba-redd', synthetic: true, min_donors: 10 });

    expect(submission.run_id).toBe('run-1');
    expect(sent[0].method).toBe('POST');
    expect(sent[0].url).toBe(`${BASE}/jobs`);
    expect(JSON.parse(sent[0].body)).toEqual({ case_id: 'kariba-redd', synthetic: true, min_donors: 10 });
  });

  it('turns an error status into an ApiRequestError with the code and remediation', async () => {
    const { api } = fakeApi(
      json(503, {
        detail: { code: 'store_not_configured', message: 'No database.', hint: 'Set DATABASE_URL.' },
      }),
    );
    const error = await api.submit({ case_id: 'kariba-redd' }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({ status: 503, code: 'store_not_configured', remediation: 'Set DATABASE_URL.' });
  });

  it('turns a network failure into ApiUnreachableError, never into data', async () => {
    const { api } = fakeApi(new TypeError('Failed to fetch'));
    const error = await api.status('run-1').catch((e) => e);
    expect(error).toBeInstanceOf(ApiUnreachableError);
    expect(error.apiBaseUrl).toBe(BASE);
  });

  it('asks for the stored run with its deterministic report', async () => {
    const { api, sent } = fakeApi(json(200, { run_id: 'run-1' }));
    await api.result('run-1', true);
    expect(sent[0].url).toBe(`${BASE}/runs/run-1?include_report=true`);
  });

  it('cancels by run id', async () => {
    const { api, sent } = fakeApi(json(202, job({ status: 'running', result_state: 'running', cancel_requested: true })));
    const view = await api.cancel('run-1');
    expect(view.cancel_requested).toBe(true);
    expect(sent[0]).toMatchObject({ method: 'POST', url: `${BASE}/jobs/run-1/cancel` });
  });
});

describe('watchJob', () => {
  it('polls about once a second until the API says terminal, reporting every status', async () => {
    const running = job({ status: 'running', result_state: 'running' });
    const done = job({ status: 'succeeded', result_state: 'measured', terminal: true });
    const { api } = fakeApi(json(200, job()), json(200, running), json(200, done));
    const time = fakeTime();
    const seen: string[] = [];

    const finished = await watchJob(api, 'run-1', {
      onUpdate: (j) => seen.push(j.result_state),
      sleep: time.sleep,
      now: time.now,
    });

    expect(finished.result_state).toBe('measured');
    expect(seen).toEqual(['queued', 'running', 'measured']);
    expect(time.sleeps).toEqual([1000, 1000]); // none after the terminal status
  });

  it('a refusal is terminal like any other outcome', async () => {
    const refused = job({ status: 'succeeded', result_state: 'refused', terminal: true });
    const { api } = fakeApi(json(200, refused));
    const finished = await watchJob(api, 'run-1', { onUpdate: () => {}, sleep: async () => {} });
    expect(finished.result_state).toBe('refused');
  });

  it('backs off 1, 2, 4, 8, then 10 s while the API is unreachable, and recovers', async () => {
    const down = () => new TypeError('Failed to fetch');
    const { api } = fakeApi(
      down(), down(), down(), down(), down(), // 1+2+4+8+10 = 25 s without contact
      json(200, job({ status: 'succeeded', result_state: 'measured', terminal: true })),
    );
    const time = fakeTime();
    const finished = await watchJob(api, 'run-1', { onUpdate: () => {}, sleep: time.sleep, now: time.now });
    expect(finished.terminal).toBe(true);
    expect(time.sleeps).toEqual([1000, 2000, 4000, 8000, 10000]);
  });

  it('gives up with LostContactError after 30 s with no answer', async () => {
    const down = () => new TypeError('Failed to fetch');
    const { api } = fakeApi(down(), down(), down(), down(), down(), down(), down());
    const time = fakeTime();
    const error = await watchJob(api, 'run-1', { onUpdate: () => {}, sleep: time.sleep, now: time.now }).catch(
      (e) => e,
    );
    expect(error).toBeInstanceOf(LostContactError);
    expect(error.runId).toBe('run-1');
    expect(time.now()).toBeGreaterThanOrEqual(30000);
  });

  it('treats a 5xx as transient but stops at once on an unknown run', async () => {
    const { api } = fakeApi(
      json(502, '<html>Bad gateway</html>'),
      json(404, { detail: { code: 'run_not_found', message: "No job 'run-1'.", hint: null } }),
    );
    const time = fakeTime();
    const error = await watchJob(api, 'run-1', { onUpdate: () => {}, sleep: time.sleep, now: time.now }).catch(
      (e) => e,
    );
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error.code).toBe('run_not_found');
    expect(time.sleeps).toEqual([1000]);
  });

  it('does not wait out a store that is not configured', async () => {
    const { api } = fakeApi(
      json(503, { detail: { code: 'store_not_configured', message: 'No database.', hint: 'Set it.' } }),
    );
    const error = await watchJob(api, 'run-1', { onUpdate: () => {}, sleep: async () => {} }).catch((e) => e);
    expect(error.code).toBe('store_not_configured');
  });

  it('refuses to show a run that belongs to another case', async () => {
    const { api } = fakeApi(json(200, job({ case_id: 'southern-cardamom-redd' })));
    const seen: JobView[] = [];
    const error = await watchJob(api, 'run-1', {
      caseId: 'kariba-redd',
      onUpdate: (j) => seen.push(j),
      sleep: async () => {},
    }).catch((e) => e);
    expect(error.code).toBe('run_case_mismatch');
    expect(seen).toEqual([]);
  });

  it('stops when aborted, with no further requests', async () => {
    const controller = new AbortController();
    const { api, sent } = fakeApi(json(200, job()), json(200, job()));
    const error = await watchJob(api, 'run-1', {
      signal: controller.signal,
      onUpdate: () => controller.abort(),
      sleep: async (_ms, signal) => {
        if (signal?.aborted) throw new DOMException('stopped', 'AbortError');
      },
    }).catch((e) => e);
    expect(error.name).toBe('AbortError');
    expect(sent).toHaveLength(1);
  });
});

describe('mapping a finished job onto the page', () => {
  it("a refusal keeps the engine's own code, stage, remediation and detail", () => {
    const refusal = refusalFromJob(
      job({
        status: 'succeeded',
        result_state: 'refused',
        terminal: true,
        error: {
          code: 'donor_pool_inadequate',
          message: 'Only 7 donors were admitted.',
          stage: 'matching',
          detail: { min_donors_required: 500 },
          remediation: 'Widen the search region.',
          is_refusal: true,
        },
      }),
    );
    expect(refusal).toEqual({
      message: 'Only 7 donors were admitted.',
      code: 'donor_pool_inadequate',
      stage: 'matching',
      remediation: 'Widen the search region.',
      runId: 'run-1',
      detail: { min_donors_required: 500 },
    });
  });

  it('a failure before the engine ran shows why it failed', () => {
    const failure = failureFromJob(
      job({ status: 'failed', result_state: 'failed', terminal: true, failure_reason: 'lease expired 3 times' }),
    );
    expect(failure).toMatchObject({ code: null, message: 'lease expired 3 times' });
  });

  it('a stored run with a bundle becomes a renderable result; without one it does not', () => {
    const bundle = KARIBA_COMPLETED.verification.bundle as unknown as EvidenceBundle;
    const run = {
      run_id: 'run-1',
      spec_hash: 'abc',
      is_simulated: true,
      bundle,
      report_markdown: '# Report',
      report_generator: 'deterministic',
    } as RunDetail;

    expect(displayedResultFromRun(run)).toEqual({
      run_id: 'run-1',
      spec_hash: 'abc',
      data_mode: 'simulated',
      bundle,
      report_markdown: '# Report',
      report_generator: 'deterministic',
    });
    expect(displayedResultFromRun({ ...run, bundle: null })).toBeNull();
  });

  it('shows only the stages the API observed, with times, and invents none', () => {
    const stages = loadingStagesFromJob(
      job({
        status: 'running',
        result_state: 'running',
        stages: [
          { name: 'claim', label: 'Claimed by a worker', state: 'done', started_at: null, finished_at: null, duration_ms: 12, elapsed_ms: null },
          { name: 'data', label: 'Resolving data access', state: 'done', started_at: null, finished_at: null, duration_ms: 1500, elapsed_ms: null },
          { name: 'engine', label: 'Running the analysis engine', state: 'active', started_at: null, finished_at: null, duration_ms: null, elapsed_ms: 2300 },
          { name: 'record', label: 'Recording the result', state: 'pending', started_at: null, finished_at: null, duration_ms: null, elapsed_ms: null },
        ],
      }),
    );
    expect(stages).toEqual([
      { id: 'claim', label: '1. CLAIMED BY A WORKER', state: 'done', desc: 'Done in 12 ms' },
      { id: 'data', label: '2. RESOLVING DATA ACCESS', state: 'done', desc: 'Done in 1.5 s' },
      { id: 'engine', label: '3. RUNNING THE ANALYSIS ENGINE', state: 'active', desc: 'In progress for 2.3 s' },
      { id: 'record', label: '4. RECORDING THE RESULT', state: 'pending', desc: 'Not started yet' },
    ]);
    expect(loadingStagesFromJob(job())).toEqual([]);
  });
});
