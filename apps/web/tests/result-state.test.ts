import { describe, it, expect } from 'vitest';
import { deriveResultState, resultStateTone, resultStateLabel, ResultState } from '../src/lib/types';

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
});

describe('resultStateTone / resultStateLabel', () => {
  const allStates: ResultState[] = ['not_started', 'running', 'measured', 'refused', 'failed'];

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
});
