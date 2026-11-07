'use client';

import { useEffect, useState } from 'react';
import { ApiUnreachableError, getCaseDetail, getVisualizationFixture } from '../../../lib/api';
import { createJobsApi, failureFrom, type ApiFailure } from '../../../lib/jobs';
import type { VerificationFixtureData } from '../../../lib/fixtures/simulated-data';
import type { CaseDetail, Evidence } from '../../../lib/types';

export type CaseEvidenceState =
  | { status: 'loading' }
  | { status: 'error'; failure: ApiFailure }
  | { status: 'no-run'; caseDetail: CaseDetail | null }
  | {
      status: 'ready';
      caseDetail: CaseDetail | null;
      items: Evidence[];
      /** Series the API does not serve yet; present only for the demo fixture. */
      viz: VerificationFixtureData | null;
      isDemo: boolean;
      runId: string | null;
    };

/**
 * Loads what the evidence and robustness pages show. Sources, in order:
 * the demo fixture (only when NEXT_PUBLIC_DEMO_MODE is on), then a stored run
 * named by `?run=<id>`. With neither, the state is `no-run`, never a guess.
 * An unreachable API with demo off is an `error` the page must display.
 */
export function useCaseEvidence(caseId: string): CaseEvidenceState {
  const [state, setState] = useState<CaseEvidenceState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    const set = (s: CaseEvidenceState) => {
      if (!cancelled) setState(s);
    };
    (async () => {
      let caseDetail: CaseDetail | null = null;
      let isDemo = false;
      try {
        const res = await getCaseDetail(caseId);
        caseDetail = res.data;
        isDemo = res.isDemo;
      } catch (err) {
        set({ status: 'error', failure: failureFrom(err, window.location.origin) });
        return;
      }
      const fixture = getVisualizationFixture(caseId);
      if (fixture) {
        set({ status: 'ready', caseDetail, items: fixture.verification.bundle.items, viz: fixture, isDemo: true, runId: null });
        return;
      }
      const runId = new URLSearchParams(window.location.search).get('run');
      if (!runId) {
        set({ status: 'no-run', caseDetail });
        return;
      }
      try {
        const run = await createJobsApi().result(runId, false);
        set({ status: 'ready', caseDetail, items: run.bundle?.items ?? [], viz: null, isDemo, runId });
      } catch (err) {
        set({
          status: 'error',
          failure: err instanceof ApiUnreachableError || err instanceof Error
            ? failureFrom(err, window.location.origin)
            : { code: null, message: 'The stored run could not be loaded.', remediation: null, status: null },
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  return state;
}
