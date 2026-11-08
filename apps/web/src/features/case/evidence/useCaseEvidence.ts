'use client';

import { useEffect, useState } from 'react';
import { ApiUnreachableError, getCaseDetail, getVisualizationFixture } from '../../../lib/api';
import { createJobsApi, failureFrom, type ApiFailure } from '../../../lib/jobs';
import type { VerificationFixtureData } from '../../../lib/fixtures/simulated-data';
import type { CaseDetail, Evidence } from '../../../lib/types';
import { chooseEvidenceSource, type EvidenceOrigin } from './provenance';

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
      /** Which source produced the items: the precomputed fixture, or the run the reader named. */
      origin: EvidenceOrigin;
    };

/**
 * Loads what the evidence and robustness pages show. Sources, in order:
 * a stored run named by `?run=<id>` (always wins, so a newly completed run is
 * never replaced by an older fixture), then the precomputed demo fixture (only
 * when NEXT_PUBLIC_DEMO_MODE is on). With neither, the state is `no-run`, never
 * a guess. A named run that cannot be loaded is an `error`, never the fixture.
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
      try {
        const res = await getCaseDetail(caseId);
        caseDetail = res.data;
      } catch (err) {
        set({ status: 'error', failure: failureFrom(err, window.location.origin) });
        return;
      }
      const fixture = getVisualizationFixture(caseId);
      const runId = new URLSearchParams(window.location.search).get('run');
      const source = chooseEvidenceSource(runId, fixture !== null);
      if (source === 'precomputed-fixture' && fixture) {
        set({ status: 'ready', caseDetail, items: fixture.verification.bundle.items, viz: fixture, isDemo: true, runId: null, origin: 'precomputed-fixture' });
        return;
      }
      if (source === 'none' || !runId) {
        set({ status: 'no-run', caseDetail });
        return;
      }
      try {
        const run = await createJobsApi().result(runId, false);
        set({ status: 'ready', caseDetail, items: run.bundle?.items ?? [], viz: null, isDemo: false, runId, origin: 'fresh-run' });
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
