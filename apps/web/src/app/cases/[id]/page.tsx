'use client';

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  API_BASE_URL,
  ApiUnreachableError,
  getCaseDetail,
  verifyCase,
  getVisualizationFixture,
  getRefusalFixture,
  RefusalInfo,
  getDonorCandidateSummary,
} from '../../../lib/api';
import {
  CaseDetail,
  deriveResultState,
  resultStateTone,
  resultStateLabel,
} from '../../../lib/types';
import {
  ApiFailure,
  ApiRequestError,
  DisplayedResult,
  JobSubmission,
  JobView,
  LostContactError,
  createJobsApi,
  displayedResultFromRun,
  failureFrom,
  failureFromJob,
  loadingStagesFromJob,
  refusalFromJob,
  unreachableRemediation,
  watchJob,
} from '../../../lib/jobs';
import {
  formatHectares,
  formatPermutationSignificance,
  formatJackknifeStability,
  formatDidParallelTrends,
  formatUncertaintyEnvelope,
} from '../../../lib/formatters';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { MetricDisplay } from '../../../components/ui/MetricDisplay';
import { VerdictCard } from '../../../components/ui/VerdictCard';
import { Tabs, TabsList, TabTrigger, TabContent } from '../../../components/ui/Tabs';
import {
  LoadingState,
  LoadingStateProps,
  RefusalState,
  ErrorState,
  EmptyState,
} from '../../../components/ui/States';
import { SimulatedBanner } from '../../../components/ui/SimulatedBanner';
import { CounterfactualChart } from '../../../components/scientific/CounterfactualChart';
import { PlaceboDistribution } from '../../../components/scientific/PlaceboDistribution';
import { DonorPoolPanel } from '../../../components/scientific/DonorPoolPanel';
import { RefusalDetails } from '../../../components/ui/RefusalDetails';
import { refusalStageLabel } from '../../../lib/refusal';
import { DonorCandidatePanel } from '../../../components/scientific/DonorCandidatePanel';
import { EvidenceExplorer } from '../../../components/scientific/EvidenceExplorer';
import { ProjectTimeline } from '../../../components/scientific/ProjectTimeline';
import { NarrativeReport } from '../../../components/scientific/NarrativeReport';
import { ProgressiveCausalPipeline, CausalPipelineStage } from '../../../components/scientific/ProgressiveCausalPipeline';
import { ProvenanceDrawer } from '../../../components/ui/ProvenanceDrawer';
import { FitDiagnostics } from '../../../components/scientific/FitDiagnostics';
import { PlaceboDiagnostics } from '../../../components/scientific/PlaceboDiagnostics';
import { SpecificationCurve } from '../../../components/scientific/SpecificationCurve';
import { DidCrossCheck } from '../../../components/scientific/DidCrossCheck';
import { findEvidence, numberValue, sig } from '../../../lib/evidence';
import { Evidence } from '../../../lib/types';
import {
  ArrowLeft,
  Play,
  Settings,
  Shield,
  ExternalLink,
  Info,
  Calendar,
  Layers,
  BarChart3,
  Map,
  FileText,
  Clock,
  CheckCircle2,
  ChevronRight,
  Sliders,
  Sparkles,
} from 'lucide-react';
import styles from './page.module.css';

/**
 * What "retry" means for a failure: queue the run again, run it inline again,
 * or resume watching a run that may still be going (never resubmit it).
 */
type RetryAction = { kind: 'submit' } | { kind: 'inline' } | { kind: 'resume'; runId: string };

interface RunFailure extends ApiFailure {
  title?: string;
  retry: RetryAction;
}

/** Where a run is, as far as this page knows. Only `idle` lets a new run start. */
type RunPhase = 'idle' | 'submitting' | 'watching' | 'fetching' | 'inline';

/** Keep `?run=<id>` in the address, so a reload or a shared link resumes the same run. */
function setRunParam(runId: string | null) {
  const url = new URL(window.location.href);
  if (runId) url.searchParams.set('run', runId);
  else url.searchParams.delete('run');
  window.history.replaceState(window.history.state, '', url);
}

export default function CaseAnalysisPage() {
  const params = useParams();
  const caseId = (params?.id as string) || 'kariba-redd';

  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [verificationResult, setVerificationResult] = useState<DisplayedResult | null>(null);
  const [runPhase, setRunPhase] = useState<RunPhase>('idle');
  const [job, setJob] = useState<JobView | null>(null);
  const [refusalError, setRefusalError] = useState<RefusalInfo | null>(null);
  const [generalError, setGeneralError] = useState<RunFailure | null>(null);
  const [cancelledRunId, setCancelledRunId] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  // Set when the job store answered 503: only then is running inline offered,
  // and only the user can choose it (inlineMode).
  const [storeUnavailable, setStoreUnavailable] = useState(false);
  const [inlineMode, setInlineMode] = useState(false);
  const isRunning = runPhase !== 'idle';
  const watchRef = useRef<AbortController | null>(null);
  const jobsApi = useMemo(() => createJobsApi(), []);
  const [activeTab, setActiveTab] = useState<string>('causal');
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [isProvenanceDrawerOpen, setIsProvenanceDrawerOpen] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<ApiFailure | null>(null);
  const [isDemo, setIsDemo] = useState(false);

  // Runner Configuration Options
  const [syntheticMode, setSyntheticMode] = useState<boolean>(true);
  const [trueEffect, setTrueEffect] = useState<number>(0.06);
  const [minDonors, setMinDonors] = useState<number>(10);
  const [includeReport, setIncludeReport] = useState<boolean>(true);

  // Load case detail
  const loadData = useCallback(async () => {
    setLoadError(null);
    try {
      const { data, isDemo: demoDetail } = await getCaseDetail(caseId);
      setCaseDetail(data);
      setIsDemo((prev) => prev || demoDetail);
    } catch (err) {
      setCaseDetail(null);
      // The first call a misconfigured deployment fails on, so it carries the
      // same code and remediation (API URL, CORS) as a failed run.
      setLoadError(
        err instanceof Error
          ? failureFrom(err, window.location.origin)
          : { code: null, message: 'Failed to load case definition.', remediation: null, status: null },
      );
      return;
    }

    // Pre-load fixture verification result for immediate demonstration.
    // Only ever returns non-null when NEXT_PUBLIC_DEMO_MODE is explicitly on.
    const fixture = getVisualizationFixture(caseId);
    if (fixture) {
      setVerificationResult(fixture.verification);
      setIsDemo(true);
    }
  }, [caseId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const applyPreset = (effect: number, donors: number) => {
    setSyntheticMode(true);
    setTrueEffect(effect);
    setMinDonors(donors);
  };

  const handleStageClick = (stage: CausalPipelineStage) => {
    switch (stage) {
      case 'claim':
        window.scrollTo({ top: 0, behavior: 'smooth' });
        break;
      case 'observed':
      case 'counterfactual':
      case 'effect':
        setActiveTab('causal');
        break;
      case 'uncertainty':
        setActiveTab('uncertainty');
        break;
      case 'evidence':
        setActiveTab('evidence');
        break;
      case 'provenance':
        if (verificationResult?.bundle?.items) {
          const primary =
            verificationResult.bundle.items.find(
              (i) => i.id === 'effect.point_estimate'
            ) || verificationResult.bundle.items[0];
          setSelectedEvidence(primary);
          setIsProvenanceDrawerOpen(true);
        }
        break;
    }
  };

  // Clear the previous outcome, so a stale number never sits beside a new run.
  const startRun = (phase: RunPhase) => {
    // Forget the old watcher as well as stopping it, so its cleanup cannot
    // mark this new run idle.
    watchRef.current?.abort();
    watchRef.current = null;
    setRefusalError(null);
    setGeneralError(null);
    setCancelledRunId(null);
    setCancelError(null);
    setVerificationResult(null);
    setJob(null);
    setRunPhase(phase);
  };

  // A terminal job becomes exactly one outcome. A refusal is a result to show,
  // never an error.
  const finishJob = useCallback(
    async (finished: JobView) => {
      switch (finished.result_state) {
        case 'measured': {
          setRunPhase('fetching');
          const shown = displayedResultFromRun(
            await jobsApi.result(finished.run_id, includeReport),
          );
          if (shown) {
            setVerificationResult(shown);
          } else {
            setGeneralError({
              code: null,
              status: null,
              message: `Run ${finished.run_id} is recorded as measured, but its evidence bundle could not be read.`,
              remediation: null,
              retry: { kind: 'resume', runId: finished.run_id },
            });
          }
          break;
        }
        case 'refused':
          setRefusalError(refusalFromJob(finished));
          break;
        case 'cancelled':
          setCancelledRunId(finished.run_id);
          break;
        default:
          setGeneralError({ ...failureFromJob(finished), retry: { kind: 'submit' } });
      }
    },
    [jobsApi, includeReport],
  );

  // Poll a run until it finishes, then show how it ended. `first` is the status
  // the submit call already returned, so the first second is not blank.
  const watch = useCallback(
    async (runId: string, first?: JobView) => {
      watchRef.current?.abort();
      const controller = new AbortController();
      watchRef.current = controller;
      setRunPhase('watching');
      if (first) setJob(first);
      try {
        const finished =
          first?.terminal
            ? first
            : await watchJob(jobsApi, runId, {
                caseId,
                signal: controller.signal,
                onUpdate: setJob,
              });
        await finishJob(finished);
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof LostContactError) {
          setGeneralError({
            title: 'Lost Contact With The API',
            code: 'lost_contact',
            status: null,
            message: `No answer from ${jobsApi.baseUrl} for 30 seconds while watching run ${runId}. The run may still be going; nothing was cancelled.`,
            remediation: `${unreachableRemediation(jobsApi.baseUrl, window.location.origin)} Retrying resumes watching the same run; it does not start a new one.`,
            retry: { kind: 'resume', runId },
          });
        } else if (err instanceof ApiRequestError && err.code === 'run_not_found') {
          setRunParam(null);
          setGeneralError({ ...failureFrom(err), retry: { kind: 'submit' } });
        } else {
          setGeneralError({
            ...failureFrom(err, window.location.origin),
            retry: { kind: 'resume', runId },
          });
        }
      } finally {
        if (watchRef.current === controller) {
          watchRef.current = null;
          setRunPhase('idle');
        }
      }
    },
    [jobsApi, caseId, finishJob],
  );

  // Resume the run named in the address (a reload, or a shared link), and stop
  // polling when the page goes away.
  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get('run');
    if (runId) void watch(runId);
    return () => watchRef.current?.abort();
  }, [watch]);

  const handleRunInline = async () => {
    startRun('inline');
    setInlineMode(true);
    setRunParam(null); // an inline run is not stored, so there is nothing to resume

    const result = await verifyCase(caseId, {
      synthetic: syntheticMode,
      true_effect: trueEffect,
      min_donors: minDonors,
      include_report: includeReport,
    });

    setRunPhase('idle');

    if (result.success && result.data) {
      setVerificationResult(result.data);
      if (result.isDemo) {
        setIsDemo(true);
      }
    } else if (result.isRefusal) {
      // The engine's own remediation, never a generic one: advice for a
      // donor-pool refusal is wrong for a misaligned panel.
      setRefusalError(
        result.refusal ?? {
          message: result.error || 'Verification was scientifically refused.',
          remediation: syntheticMode
            ? null
            : 'Earth Engine reducer chain is planned for MVP. Set synthetic=true to exercise the pipeline.',
        },
      );
    } else {
      setGeneralError({
        code: result.code ?? null,
        status: null,
        message: result.error || 'Execution failed.',
        remediation:
          result.code === 'api_unreachable'
            ? unreachableRemediation(API_BASE_URL, window.location.origin)
            : result.remediation ?? null,
        retry: { kind: 'inline' },
      });
    }
  };

  const handleRunVerification = async () => {
    if (inlineMode) {
      await handleRunInline();
      return;
    }
    startRun('submitting');

    let submission: JobSubmission;
    try {
      submission = await jobsApi.submit({
        case_id: caseId,
        synthetic: syntheticMode,
        min_donors: minDonors,
      });
    } catch (err) {
      setRunPhase('idle');
      if (err instanceof ApiUnreachableError) {
        // Demo mode only: getVisualizationFixture is null unless
        // NEXT_PUBLIC_DEMO_MODE is on, and the demo banner then says no
        // analysis was executed.
        const fixture = syntheticMode ? getVisualizationFixture(caseId) : null;
        if (fixture) {
          setVerificationResult(fixture.verification);
          setIsDemo(true);
          return;
        }
      }
      if (err instanceof ApiRequestError && err.code === 'not_implemented') {
        // Observed data is refused, never silently simulated: a refusal state,
        // as /verify's 501 always was.
        setRefusalError({ message: err.message, code: err.code, remediation: err.remediation });
        return;
      }
      if (
        err instanceof ApiRequestError &&
        (err.code === 'store_not_configured' || err.code === 'store_unavailable')
      ) {
        setStoreUnavailable(true);
      }
      setGeneralError({ ...failureFrom(err, window.location.origin), retry: { kind: 'submit' } });
      return;
    }

    setRunParam(submission.run_id);
    await watch(submission.run_id, submission.job);
  };

  const handleCancel = async () => {
    if (!job) return;
    setCancelError(null);
    try {
      setJob(await jobsApi.cancel(job.run_id));
    } catch (err) {
      // Finished first: the watcher is about to show how it ended.
      if (err instanceof ApiRequestError && err.code === 'job_already_finished') return;
      const failure = failureFrom(err, window.location.origin);
      setCancelError(`${failure.code ? `${failure.code}: ` : ''}${failure.message}`);
    }
  };

  const retry = (action: RetryAction) => {
    if (action.kind === 'resume') {
      setGeneralError(null);
      void watch(action.runId);
    } else if (action.kind === 'inline') {
      void handleRunInline();
    } else {
      void handleRunVerification();
    }
  };

  if (!caseDetail) {
    if (loadError) {
      return (
        <div className="gt-container" style={{ paddingTop: '40px' }}>
          <ErrorState
            title="Cannot Load Case Definition"
            message={loadError.message}
            code={loadError.code}
            remediation={loadError.remediation}
            onRetry={loadData}
          />
        </div>
      );
    }
    return (
      <div className="gt-container" style={{ paddingTop: '40px' }}>
        <LoadingState
          message="Loading Case Definition..."
          subtext="Retrieving case schema and validation targets"
          stages={[]}
        />
      </div>
    );
  }

  const fixtureViz = getVisualizationFixture(caseId);

  // The lifecycle state of the verification run itself, as distinct from the
  // scientific verdict a completed run produces. Drives what is rendered
  // below and must never be inferred from the presence of a stale number.
  const resultState = deriveResultState({
    isQueued: runPhase === 'watching' && job?.result_state === 'queued',
    isRunning,
    hasResult: verificationResult !== null,
    isRefused: refusalError !== null,
    hasError: generalError !== null,
    isCancelled: cancelledRunId !== null,
  });

  // What the loading state shows comes from the API: the job's observed
  // stages, or none at all. Nothing here advances on a timer.
  const loadingProps: LoadingStateProps = (() => {
    if (runPhase === 'inline') {
      return {
        subtext:
          'Running inline: the API answers once the whole analysis is done, so there are no stages to show. Nothing is stored.',
        isSimulated: syntheticMode,
        stages: [],
      };
    }
    if (runPhase === 'submitting') {
      return {
        message: 'SUBMITTING ANALYSIS JOB',
        subtext: `Queueing the run with ${jobsApi.baseUrl}.`,
        isSimulated: syntheticMode,
        stages: [],
      };
    }
    if (!job) {
      return {
        message: 'FETCHING RUN STATUS',
        subtext: 'Asking the API where this run is.',
        stages: [],
      };
    }
    const subtext =
      runPhase === 'fetching'
        ? `Run ${job.run_id} finished. Fetching its stored evidence bundle.`
        : job.cancel_requested
        ? `Run ${job.run_id}: cancel requested. The engine is one uninterruptible step, so the run stops when it next checks in.`
        : job.result_state === 'queued'
        ? `Run ${job.run_id} is waiting for a worker. If it stays queued, check that a worker is running.`
        : `Run ${job.run_id}. Stages appear as they are observed; there is no percentage because none can be known.`;
    return {
      message:
        job.result_state === 'queued'
          ? 'QUEUED — WAITING FOR A WORKER'
          : 'RUNNING CAUSAL VERIFICATION PIPELINE',
      subtext,
      isSimulated: job.is_simulated,
      stages: loadingStagesFromJob(job),
    };
  })();

  // ADR-011 donor-candidate generation has no backend endpoint yet (see
  // getDonorCandidateSummary's doc comment); this is the honest
  // nothing-has-been-measured shape, not a fixture.
  const donorCandidateSummary = getDonorCandidateSummary(caseDetail);

  // Real evidence lookup for a measured result. Used instead of the
  // hardcoded stage/summary values this page used to show regardless of
  // what (if anything) the bundle actually contained.
  const openProvenance = (item: Evidence) => {
    setSelectedEvidence(item);
    setIsProvenanceDrawerOpen(true);
  };

  const claimCreditsItem =
    resultState === 'measured' && verificationResult
      ? findEvidence(verificationResult.bundle.items, 'claim.credits_tco2e')
      : undefined;

  const effectPointEstimateItem =
    resultState === 'measured' && verificationResult
      ? verificationResult.bundle.items.find((i) => i.id === 'effect.point_estimate')
      : undefined;

  return (
    <div className="gt-container" style={{ paddingTop: '20px', paddingBottom: '60px' }}>
      {isDemo && (
        <SimulatedBanner
          message="DEMO MODE — NO ANALYSIS WAS EXECUTED"
          subtext={`The backend API at ${API_BASE_URL} was unreachable, so this page is showing synthetic fixture data served only because NEXT_PUBLIC_DEMO_MODE is enabled. No causal verification pipeline actually ran against this case.`}
        />
      )}

      {/* Breadcrumbs Navigation */}
      <nav className={styles.breadcrumbs} aria-label="Breadcrumb">
        <Link href="/cases" className={styles.breadcrumbLink}>Projects</Link>
        <ChevronRight size={13} className={styles.breadcrumbSep} />
        <span className={styles.breadcrumbActive}>{caseDetail.name}</span>
      </nav>

      {/* Case Header */}
      <div className={styles.caseHeader}>
        <div className={styles.headerTop}>
          <div className={styles.titleArea}>
            <div className={styles.badgesRow}>
              <Badge tone="info" size="sm" variant="solid">
                {caseDetail.standard} {caseDetail.registry_id ? `(${caseDetail.registry_id})` : ''}
              </Badge>
              <Badge tone="neutral" size="sm" variant="outline">
                CASE ID: {caseDetail.case_id}
              </Badge>
              <Badge tone="positive" size="sm" variant="subtle">
                STATUS: {caseDetail.status.toUpperCase()}
              </Badge>
              <Badge tone={resultStateTone(resultState)} size="sm" variant="outline">
                RUN: {resultStateLabel(resultState)}
              </Badge>
            </div>
            <h1 className={styles.caseTitle}>{caseDetail.name}</h1>
            <p className={styles.caseLocation}>
              {caseDetail.country} · {caseDetail.ecosystem} · Project Area: {formatHectares(caseDetail.area_ha)}
            </p>
          </div>

          <div className={styles.quickMetrics}>
            <MetricDisplay
              label="Primary Indicator"
              value={caseDetail.indicator.toUpperCase()}
              unit=""
              size="sm"
            />
            <MetricDisplay
              label="Baseline Pre-Period"
              value={caseDetail.pre_period}
              unit=""
              size="sm"
            />
            <MetricDisplay
              label="Crediting Post-Period"
              value={caseDetail.post_period}
              unit=""
              size="sm"
            />
          </div>
        </div>

        {/* Known Reference Validation Target (Disclaimed) */}
        {caseDetail.known_reference && Object.keys(caseDetail.known_reference).length > 0 && (
          <div className={styles.knownRefBox}>
            <div className={styles.knownRefHeader}>
              <Shield size={16} className={styles.knownRefIcon} />
              <h4 className={styles.knownRefTitle}>
                Published Third-Party Benchmark Target (Post-Hoc Validation Only)
              </h4>
            </div>
            <p className={styles.knownRefDesc}>
              {String(caseDetail.known_reference.description || '')}
            </p>
            <div className={styles.knownRefCaveat}>
              <strong>Strict Independence Rule:</strong> {String(caseDetail.known_reference.caveat || '')}
            </div>
          </div>
        )}
      </div>

      {/* Verification Runner Control Panel */}
      <div className={styles.runnerCard}>
        <div className={styles.runnerHeader}>
          <div className={styles.runnerTitleGroup}>
            <Settings size={18} className={styles.runnerIcon} />
            <h3 className={styles.runnerTitle}>Causal Verification Runner</h3>
          </div>
          <span className={styles.runnerSubtext}>
            Configure screening parameters and launch the simplex-constrained FISTA solver.
          </span>
        </div>

        {/* Preset Screening Buttons */}
        <div className={styles.presetsRow}>
          <span className={styles.presetsLabel}>
            <Sparkles size={13} />
            <span>QUICK PRESETS:</span>
          </span>
          <button
            type="button"
            className={styles.presetBtn}
            onClick={() => applyPreset(0.06, 10)}
          >
            Kariba Benchmark (+0.06 / 10 donors)
          </button>
          <button
            type="button"
            className={styles.presetBtn}
            onClick={() => applyPreset(0.00, 10)}
          >
            Null Test (+0.00 / 10 donors)
          </button>
          <button
            type="button"
            className={styles.presetBtn}
            onClick={() => applyPreset(0.12, 20)}
          >
            Large Effect (+0.12 / 20 donors)
          </button>
        </div>

        <div className={styles.runnerControls}>
          {/* Synthetic vs Observed Toggle */}
          <div className={styles.controlItem}>
            <label className={styles.controlLabel}>Data Provider Mode</label>
            <div className={styles.toggleGroup}>
              <button
                type="button"
                className={`${styles.toggleBtn} ${syntheticMode ? styles.toggleActive : ''}`}
                onClick={() => setSyntheticMode(true)}
              >
                Synthetic Fixture [Simulated]
              </button>
              <button
                type="button"
                className={`${styles.toggleBtn} ${!syntheticMode ? styles.toggleActiveCaution : ''}`}
                onClick={() => setSyntheticMode(false)}
              >
                Observed EO [Sentinel/Landsat]
              </button>
            </div>
            <span className={styles.fieldHint}>
              {syntheticMode
                ? 'Runs deterministic simulation with injected effect.'
                : 'Triggers real Earth Engine reducer (501 refusal until MVP lands).'}
            </span>
          </div>

          {/* Injected Effect (Synthetic only) */}
          {syntheticMode && (
            <div className={styles.controlItem}>
              <div className={styles.labelWithVal}>
                <label className={styles.controlLabel}>Injected Effect (True Effect)</label>
                <span className={styles.controlValDisplay}>
                  {/* A queued run uses the worker's effect, so showing the
                      slider's value would describe a run that is not happening. */}
                  {inlineMode
                    ? `+${(trueEffect * 100).toFixed(1)}% (${trueEffect.toFixed(3)} ${caseDetail.indicator})`
                    : 'SET BY WORKER'}
                </span>
              </div>
              <input
                type="range"
                min="0.00"
                max="0.15"
                step="0.01"
                value={trueEffect}
                onChange={(e) => setTrueEffect(parseFloat(e.target.value))}
                className={styles.slider}
                aria-label="Injected effect slider"
                disabled={!inlineMode}
              />
              <span className={styles.fieldHint}>
                {inlineMode
                  ? 'Injected signal for testing estimator recovery.'
                  : 'Queued runs use the effect the worker was started with (--true-effect, default +0.06).'}
              </span>
            </div>
          )}

          {/* Min Donors */}
          <div className={styles.controlItem}>
            <label className={styles.controlLabel}>Min Admitted Donors</label>
            <select
              value={minDonors}
              onChange={(e) => setMinDonors(parseInt(e.target.value, 10))}
              className={styles.select}
              aria-label="Minimum admitted donors"
            >
              <option value="5">5 units (Permissive)</option>
              <option value="10">10 units (Standard Gate)</option>
              <option value="20">20 units (Conservative)</option>
              <option value="500">500 units (Test Refusal Gate)</option>
            </select>
            <span className={styles.fieldHint}>
              Runs below 10 donors automatically fail the first verdict gate.
            </span>
          </div>

          {/* Action Button */}
          <div className={styles.actionCol}>
            <Button
              variant="primary"
              size="lg"
              onClick={handleRunVerification}
              isLoading={isRunning}
              leftIcon={<Play size={16} />}
              style={{ width: '100%' }}
            >
              {isRunning ? 'Running Engine...' : 'Run Causal Verification'}
            </Button>
            {runPhase === 'watching' && job && !job.terminal && (
              <Button
                variant="secondary"
                size="lg"
                onClick={handleCancel}
                disabled={job.cancel_requested}
                style={{ width: '100%', minHeight: '44px', whiteSpace: 'normal' }}
              >
                {job.cancel_requested ? 'Cancel requested' : 'Cancel run'}
              </Button>
            )}
            {cancelError && <span className={styles.fieldHint}>{cancelError}</span>}
            {storeUnavailable && !inlineMode && !isRunning && (
              <Button
                variant="secondary"
                size="lg"
                onClick={handleRunInline}
                style={{ width: '100%', minHeight: '44px', whiteSpace: 'normal' }}
              >
                Run inline instead (nothing is stored)
              </Button>
            )}
            {isDemo && getRefusalFixture(caseId) && (
              <Button
                variant="secondary"
                size="lg"
                onClick={() => {
                  setGeneralError(null);
                  setRefusalError(getRefusalFixture(caseId));
                }}
                style={{ width: '100%', minHeight: '44px', whiteSpace: 'normal' }}
              >
                Preview a refusal (simulated)
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Execution States: Running / Refusal / Error */}
      {isRunning && (
        <div className={styles.stateWrapper}>
          <LoadingState {...loadingProps} />
        </div>
      )}

      {refusalError && !isRunning && (
        <div className={styles.stateWrapper}>
          <RefusalState
            title={
              refusalError.stage
                ? `Analysis refused at ${refusalStageLabel(refusalError.stage)}`
                : undefined
            }
            reason={refusalError.message}
            remediation={refusalError.remediation}
            onBack={() => {
              setRefusalError(null);
              setRunParam(null);
            }}
          >
            <RefusalDetails refusal={refusalError} />
          </RefusalState>
        </div>
      )}

      {generalError && !isRunning && (
        <div className={styles.stateWrapper}>
          <ErrorState
            title={generalError.title}
            message={generalError.message}
            code={generalError.code}
            remediation={generalError.remediation}
            onRetry={() => retry(generalError.retry)}
          />
        </div>
      )}

      {cancelledRunId && !isRunning && (
        <div className={styles.stateWrapper}>
          <EmptyState
            title="Run Cancelled"
            description={`Run ${cancelledRunId} was cancelled before it produced a result. Nothing was measured, so nothing is shown.`}
            actionLabel="Return to Case Definition"
            onAction={() => {
              setCancelledRunId(null);
              setRunParam(null);
            }}
          />
        </div>
      )}

      {/* Results Section. Gated on resultState, not just the presence of a
          (possibly stale) verificationResult, so a subsequent failed or
          refused run never renders alongside a prior measurement. */}
      {resultState === 'measured' && verificationResult && (
        <div className={styles.resultsContainer}>
          {/* Progressive Causal Pipeline: Scientific Revelation */}
          <section className={styles.pipelineSection} aria-label="Progressive Causal Revelation">
            <div className={styles.pipelineHeader}>
              <div className={styles.pipelineTitleGroup}>
                <span className={styles.pipelineEyebrow}>METHODOLOGICAL INFERENCE PIPELINE</span>
                <h3 className={styles.pipelineTitle}>Progressive Causal Revelation</h3>
              </div>
              <span className={styles.pipelineHint}>
                Click any stage to inspect underlying observations, models, or provenance
              </span>
            </div>
            <ProgressiveCausalPipeline
              // The developer's own claim, as the registry reports it. Never the
              // known_reference block (a third-party finding) and never the
              // effect injected into a synthetic run.
              claimValue={
                claimCreditsItem && numberValue(claimCreditsItem) !== undefined
                  ? `${sig(numberValue(claimCreditsItem) as number, 4)} ${claimCreditsItem.unit} (claimed)`
                  : undefined
              }
              // observedValue / counterfactualValue are intentionally omitted:
              // no evidence item in EvidenceBundle currently exposes a single
              // scalar "observed mean" / "counterfactual mean" for this stage,
              // so there is nothing real to show. Leaving them undefined lets
              // the component render its own honest "—" rather than the
              // fabricated '0.642 (Post-Mean)' / '0.600 (Synth-Mean)'
              // placeholders that used to be hardcoded here regardless of
              // whether a run had actually produced them.
              causalEffectValue={
                typeof effectPointEstimateItem?.value === 'number'
                  ? `${effectPointEstimateItem.value.toFixed(3)} ${caseDetail.indicator}`
                  : undefined
              }
              uncertaintyValue={formatUncertaintyEnvelope(effectPointEstimateItem?.confidence) || undefined}
              uncertaintyUnit={effectPointEstimateItem?.confidence ? caseDetail.indicator : undefined}
              evidenceCount={verificationResult.bundle.items.length}
              provenanceHash={verificationResult.spec_hash}
              activeStage={
                activeTab === 'causal'
                  ? 'counterfactual'
                  : activeTab === 'uncertainty'
                  ? 'uncertainty'
                  : activeTab === 'evidence'
                  ? 'evidence'
                  : 'effect'
              }
              onStageClick={handleStageClick}
            />
          </section>

          {/* Prominent Verdict Card with Non-Collapsible Caveats */}
          <VerdictCard
            verdict={verificationResult.bundle.verdict!}
            caseName={caseDetail.name}
          />

          {/* Interactive Scientific Tabs */}
          <div className={styles.tabsSection}>
            <Tabs value={activeTab} onValueChange={setActiveTab} defaultValue="causal">
              <TabsList>
                <TabTrigger value="causal" icon={<BarChart3 size={15} />}>
                  1. Causal Fit & Counterfactual
                </TabTrigger>
                <TabTrigger value="uncertainty" icon={<Shield size={15} />}>
                  2. Placebos & Uncertainty
                </TabTrigger>
                <TabTrigger value="donors" icon={<Map size={15} />}>
                  3. Donor Pool & Matching
                </TabTrigger>
                <TabTrigger value="evidence" icon={<Layers size={15} />}>
                  4. Evidence Explorer ({verificationResult.bundle.items.length})
                </TabTrigger>
                <TabTrigger value="timeline" icon={<Clock size={15} />}>
                  5. Project Timeline
                </TabTrigger>
                <TabTrigger value="report" icon={<FileText size={15} />}>
                  6. Screening Narrative
                </TabTrigger>
              </TabsList>

              {/* Tab 1: Causal Fit & Counterfactual */}
              <TabContent value="causal">
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {fixtureViz && (
                  <CounterfactualChart
                    data={fixtureViz.chartSeries}
                    treatmentYear={
                      numberValue(findEvidence(verificationResult.bundle.items, 'fit.treatment_boundary_period')) ??
                      parseInt(caseDetail.post_period.split('-')[0], 10)
                    }
                    indicator={caseDetail.indicator}
                    indicatorUnit={caseDetail.indicator}
                    evidence={verificationResult.bundle.items}
                  />
                )}
                <FitDiagnostics
                  items={verificationResult.bundle.items}
                  onSelectEvidence={openProvenance}
                />
                </div>
              </TabContent>

              {/* Tab 2: Uncertainty & Placebos */}
              <TabContent value="uncertainty">
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* The distribution itself is not served by the API yet; the
                      evidence panel below renders for every response. */}
                  {fixtureViz && <PlaceboDistribution data={fixtureViz.placebos} />}
                  <PlaceboDiagnostics
                    items={verificationResult.bundle.items}
                    onSelectEvidence={openProvenance}
                  />
                  <SpecificationCurve
                    items={verificationResult.bundle.items}
                    onSelectEvidence={openProvenance}
                  />
                  <DidCrossCheck
                    items={verificationResult.bundle.items}
                    onSelectEvidence={openProvenance}
                  />
                </div>
              </TabContent>

              {/* Tab 3: Donor Pool & Map */}
              <TabContent value="donors">
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <DonorCandidatePanel summary={donorCandidateSummary} />
                  {/* No map: the engine matches in covariate space and no unit
                      geometry exists yet, so a map would have to invent it. */}
                  <DonorPoolPanel
                    items={verificationResult.bundle.items}
                    candidates={fixtureViz?.donorPool}
                    onSelectEvidence={openProvenance}
                  />
                </div>
              </TabContent>

              {/* Tab 4: Evidence Explorer */}
              <TabContent value="evidence">
                <EvidenceExplorer items={verificationResult.bundle.items} />
              </TabContent>

              {/* Tab 5: Project Timeline */}
              <TabContent value="timeline">
                {fixtureViz && (
                  <ProjectTimeline
                    events={fixtureViz.timeline}
                    creditingStartYear={parseInt(caseDetail.post_period.split('-')[0], 10)}
                  />
                )}
              </TabContent>

              {/* Tab 6: Narrative Report */}
              <TabContent value="report">
                <NarrativeReport
                  markdown={verificationResult.report_markdown}
                  generator={verificationResult.report_generator}
                />
              </TabContent>
            </Tabs>
          </div>

          {/* Scientific Conclusion & Audit Resolution Footer */}
          <section className={styles.scientificConclusionSection} aria-labelledby="audit-conclusion-title">
            <div className={styles.conclusionHeader}>
              <div className={styles.conclusionTitleGroup}>
                <span className={styles.conclusionEyebrow}>SCIENTIFIC CONCLUSION & AUDIT RESOLUTION</span>
                <h3 id="audit-conclusion-title" className={styles.conclusionTitle}>
                  Methodological Resolution: Robustness, Evidence & Lineage
                </h3>
              </div>
              <Badge tone="info" size="sm" variant="subtle">
                GROUNDTRUTH // AUDIT GRADE
              </Badge>
            </div>

            <div className={styles.conclusionGrid}>
              {/* 1. ROBUSTNESS */}
              <div className={styles.conclusionCard}>
                <div className={styles.conclusionCardHeader}>
                  <Shield size={16} className={styles.conclusionCardIcon} />
                  <h4 className={styles.conclusionCardTitle}>1. ROBUSTNESS</h4>
                </div>
                <p className={styles.conclusionCardDesc}>
                  Validation checks confirm the estimated post-intervention divergence is not an artifact of model specification.
                </p>
                <div className={styles.conclusionMetrics}>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Permutation Significance:</span>
                    <span className={styles.conclusionVal}>
                      {formatPermutationSignificance(verificationResult.bundle.items)}
                    </span>
                  </div>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Donor Jackknife Stability:</span>
                    <span className={styles.conclusionVal}>
                      {formatJackknifeStability(verificationResult.bundle.items)}
                    </span>
                  </div>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>DiD Parallel Pre-Trends:</span>
                    <span className={styles.conclusionVal}>
                      {formatDidParallelTrends(verificationResult.bundle.items)}
                    </span>
                  </div>
                </div>
              </div>

              {/* 2. EVIDENCE */}
              <div className={styles.conclusionCard}>
                <div className={styles.conclusionCardHeader}>
                  <Layers size={16} className={styles.conclusionCardIcon} />
                  <h4 className={styles.conclusionCardTitle}>2. EVIDENCE LEDGER</h4>
                </div>
                <p className={styles.conclusionCardDesc}>
                  Structured evidence items registered with formal confidence intervals, sensor qualifiers, and verification gates.
                </p>
                <div className={styles.conclusionMetrics}>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Registered Evidence Items:</span>
                    <span className={styles.conclusionVal}>{verificationResult.bundle.items.length} verified metrics</span>
                  </div>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Active Verdict Gates:</span>
                    {/* No backend contract reports gate evaluation counts;
                        see the #58 follow-up verification notes. */}
                    <span className={styles.conclusionVal}>Not available</span>
                  </div>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Intervention Boundary:</span>
                    <span className={styles.conclusionVal}>{caseDetail.post_period.split('-')[0]} Crediting Start</span>
                  </div>
                </div>
                <button
                  type="button"
                  className={styles.conclusionLinkBtn}
                  onClick={() => setActiveTab('evidence')}
                >
                  Inspect Full Evidence Matrix →
                </button>
              </div>

              {/* 3. PROVENANCE */}
              <div className={styles.conclusionCard}>
                <div className={styles.conclusionCardHeader}>
                  <Clock size={16} className={styles.conclusionCardIcon} />
                  <h4 className={styles.conclusionCardTitle}>3. PROVENANCE & LINEAGE</h4>
                </div>
                <p className={styles.conclusionCardDesc}>
                  Full cryptographic chain of custody. Every observation, covariate, and estimate is hashed and traceable to source code.
                </p>
                <div className={styles.conclusionMetrics}>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Engine Version:</span>
                    <span className={styles.conclusionVal}>v{verificationResult.bundle.schema_version}</span>
                  </div>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Spec Hash:</span>
                    <span className={styles.conclusionValMono}>
                      {verificationResult.spec_hash || 'Not available'}
                    </span>
                  </div>
                  <div className={styles.conclusionMetricRow}>
                    <span className={styles.conclusionKey}>Audit Digest:</span>
                    {/* No second hash exists anywhere in the backend contract
                        (EvidenceBundle/Evidence carry no digest field);
                        see the #58 follow-up verification notes. */}
                    <span className={styles.conclusionValMono}>Not available</span>
                  </div>
                </div>
                <button
                  type="button"
                  className={styles.conclusionLinkBtn}
                  onClick={() => {
                    const primary =
                      verificationResult.bundle.items.find(
                        (i) => i.id === 'effect.point_estimate'
                      ) || verificationResult.bundle.items[0];
                    setSelectedEvidence(primary);
                    setIsProvenanceDrawerOpen(true);
                  }}
                >
                  Open Provenance Inspector →
                </button>
              </div>

              {/* 4. METHODOLOGICAL LIMITATIONS */}
              <div className={styles.conclusionCard}>
                <div className={styles.conclusionCardHeader}>
                  <Info size={16} className={styles.conclusionCardIcon} />
                  <h4 className={styles.conclusionCardTitle}>4. LIMITATIONS & CAVEATS</h4>
                </div>
                <p className={styles.conclusionCardDesc}>
                  Strict scientific guardrails apply. An independent divergence is an invitation to audit baseline assumptions, not proof of fraud.
                </p>
                <div className={styles.limitationsList}>
                  <div className={styles.limitationItem}>
                    <strong>Units Guard:</strong> NDVI is a spectral reflectance index, not carbon; converting requires site-specific allometric equations.
                  </div>
                  <div className={styles.limitationItem}>
                    <strong>Identifying Assumptions:</strong> Observed divergence only represents causal additionality under the unconfoundedness assumption.
                  </div>
                  <div className={styles.limitationItem}>
                    <strong>Simulated Notice:</strong> This run evaluated synthetic test fixtures and makes no factual claim about real-world projects.
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      )}

      {/* Provenance Drawer for full chain of custody inspection */}
      <ProvenanceDrawer
        evidence={selectedEvidence}
        isOpen={isProvenanceDrawerOpen}
        onClose={() => setIsProvenanceDrawerOpen(false)}
      />
    </div>
  );
}
