import { describe, it, expect, expectTypeOf } from 'vitest';
import { deriveResultState, resultStateTone, resultStateLabel, ResultState } from '../src/lib/types';
import type { JobView } from '../src/lib/jobs';

/**
 * Frontend representation of scientific result state: a verification run's
 * lifecycle (not_started / running / measured / refused / failed) as
 * distinct from the scientific verdict a completed run produces.
 */
describe('deriveResultState', () => {
  it('is not_started when nothing has happened yet', () => {
    expect(
      deriveResultState({ isRunning: false, hasResult: false, isRefused: false, hasError: false })
    ).toBe('not_started');
  });

  it('is running whenever a request is in flight, regardless of stale signals', () => {
    expect(
      deriveResultState({ isRunning: true, hasResult: false, isRefused: false, hasError: false })
    ).toBe('running');
    // A run in flight takes precedence even if a stale result/error is present.
    expect(
      deriveResultState({ isRunning: true, hasResult: true, isRefused: true, hasError: true })
    ).toBe('running');
  });

  it('is measured only when a result exists and nothing else overrides it', () => {
    expect(
      deriveResultState({ isRunning: false, hasResult: true, isRefused: false, hasError: false })
    ).toBe('measured');
  });

  it('is refused when the run was scientifically refused, even if a stale result exists', () => {
    expect(
      deriveResultState({ isRunning: false, hasResult: true, isRefused: true, hasError: false })
    ).toBe('refused');
  });

  it('is failed when the run failed for a non-scientific reason, even if a stale result exists', () => {
    expect(
      deriveResultState({ isRunning: false, hasResult: true, isRefused: false, hasError: true })
    ).toBe('failed');
  });

  it('prioritises refused over failed when both are somehow set', () => {
    expect(
      deriveResultState({ isRunning: false, hasResult: false, isRefused: true, hasError: true })
    ).toBe('refused');
  });

  it('is queued while a job waits for a worker, ahead of running', () => {
    expect(
      deriveResultState({ isQueued: true, isRunning: true, hasResult: false, isRefused: false, hasError: false })
    ).toBe('queued');
  });

  it('is cancelled when the run was stopped, even if a stale result exists', () => {
    expect(
      deriveResultState({ isRunning: false, hasResult: true, isRefused: false, hasError: false, isCancelled: true })
    ).toBe('cancelled');
  });
});

describe('resultStateTone / resultStateLabel', () => {
  const allStates: ResultState[] = [
    'not_started',
    'queued',
    'running',
    'measured',
    'refused',
    'failed',
    'cancelled',
  ];

  it('gives every state a tone and a label, with no bare-number-shaped copy', () => {
    for (const state of allStates) {
      expect(resultStateTone(state)).toBeTruthy();
      expect(resultStateLabel(state)).toBeTruthy();
      expect(resultStateLabel(state)).not.toMatch(/^\d/);
    }
  });

  it('never styles a refusal or failure as positive', () => {
    expect(resultStateTone('refused')).not.toBe('positive');
    expect(resultStateTone('failed')).not.toBe('positive');
  });

  it('styles measured as positive and failed distinctly from refused', () => {
    expect(resultStateTone('measured')).toBe('positive');
    expect(resultStateTone('refused')).not.toBe(resultStateTone('failed'));
  });

  it('never styles a cancelled run as a finding or a fault', () => {
    expect(resultStateTone('cancelled')).not.toBe('positive');
    expect(resultStateTone('cancelled')).not.toBe('error');
  });

  it("accepts the API's result_state values one to one", () => {
    // Checked by `npm run typecheck`: a state the API adds must be added here too.
    expectTypeOf<JobView['result_state']>().toMatchTypeOf<ResultState>();
    const apiStates: JobView['result_state'][] = ['queued', 'running', 'measured', 'refused', 'failed', 'cancelled'];
    expect(apiStates.map(resultStateLabel)).toEqual([
      'QUEUED', 'RUNNING', 'MEASURED', 'REFUSED', 'FAILED', 'CANCELLED',
    ]);
  });
});
