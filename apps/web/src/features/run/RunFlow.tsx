"use client";

import React, { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { Button, Card, Chip, LinkButton } from "../../components/ds";
import { ApiUnreachableError } from "../../lib/api";
import { createJobsApi, failureFrom, type JobView } from "../../lib/jobs";
import { watchJob } from "../../lib/jobs-stream";
import { BarList, RangeBar } from "../../components/charts";
import { Lens } from "../../lib/lens";
import { LensCaption } from "../case/overview/LensCaption";
import { effectRange, type RangeFigure } from "../case/overview/figures";
import { stageDurationBars } from "./durations";
import { runCopy } from "./copy";
import { initialState, reduce, stepIndex, STEP_ORDER, type Outcome } from "./machine";
import { Theatre } from "./Theatre";
import styles from "./run.module.css";

const jobsApi = createJobsApi();

/** Evidence link that names this run, so the screen shows it and never an older precomputed fixture. */
export function evidenceHref(caseId: string, runId: string | null): string {
  const base = `/cases/${caseId}/evidence`;
  return runId ? `${base}?run=${encodeURIComponent(runId)}` : base;
}

function Stepper({ index }: { index: number }) {
  return (
    <ol className={styles.stepper} aria-label="Progress">
      {STEP_ORDER.map((s, i) => (
        <li
          key={s}
          className={`${styles.step} ${i === index ? styles.stepActive : i < index ? styles.stepDone : ""}`}
          aria-current={i === index ? "step" : undefined}
        >
          <span className={styles.stepNum} aria-hidden="true">
            {i < index ? "✓" : i + 1}
          </span>
          {runCopy.steps[i]}
        </li>
      ))}
    </ol>
  );
}

function OutcomeCard({
  outcome,
  runId,
  onRetry,
}: {
  outcome: Outcome;
  runId: string | null;
  onRetry: () => void;
}) {
  return (
    <Card className={styles.outcome} role="status" data-outcome={outcome.kind}>
      <h2>{outcome.title}</h2>
      <p>{outcome.reason}</p>
      {outcome.kind === "lostContact" && runId && (
        <p className={styles.stamps}>
          Run id <code>{runId}</code>
        </p>
      )}
      <p className={styles.next}>{outcome.next}</p>
      <div className={styles.row}>
        <Button onClick={onRetry}>{runCopy.retry}</Button>
        <LinkButton variant="ghost" href="/method">
          Method
        </LinkButton>
      </div>
    </Card>
  );
}

/** The minimum the field holds, or undefined when it is empty. Never a number below 2. */
export function parseMinDonors(text: string): number | undefined | null {
  const t = text.trim();
  if (!t) return undefined;
  const n = Number(t);
  return Number.isInteger(n) && n >= 2 ? n : null;
}

export function RunFlow({ caseId, basePath }: { caseId: string; basePath?: string }) {
  const [state, dispatch] = useReducer(reduce, initialState);
  const [minDonorsText, setMinDonorsText] = useState("");
  const minDonors = parseMinDonors(minDonorsText);
  const evidenceLink = basePath ? `${basePath}/evidence` : evidenceHref(caseId, state.runId);
  const overviewLink = basePath ? `${basePath}/overview` : `/cases/${caseId}`;
  const [headline, setHeadline] = useState<string | null>(null);
  const [range, setRange] = useState<RangeFigure | null>(null);
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => () => stopRef.current?.(), []);

  const watch = useCallback((runId: string) => {
    stopRef.current?.();
    stopRef.current = watchJob(runId, {
      onProgress: (job: JobView) => dispatch({ type: "progress", job }),
      onDone: (job: JobView) => dispatch({ type: "done", job }),
      // The run was accepted; only its progress went missing. Say so, keeping its id.
      onError: (err) => dispatch({ type: "lostContact", reason: failureFrom(err).message }),
    });
  }, []);

  const start = async () => {
    dispatch({ type: "start" });
    setHeadline(null);
    setRange(null);
    try {
      const sub = await jobsApi.submit({
        case_id: caseId,
        synthetic: true,
        ...(typeof minDonors === "number" ? { min_donors: minDonors } : {}),
      });
      dispatch({ type: "submitted", job: sub.job });
      if (!sub.job.terminal) watch(sub.job.run_id);
    } catch (err) {
      dispatch({
        type: "submitFailed",
        unreachable: err instanceof ApiUnreachableError,
        reason: failureFrom(err).message,
      });
    }
  };

  const cancel = async () => {
    if (!state.runId) return;
    dispatch({ type: "cancel" });
    try {
      await jobsApi.cancel(state.runId);
    } catch {
      /* The stream or poll reports the real final state. */
    }
  };

  const measuredRunId = state.step === "results" && !state.outcome ? state.runId : null;
  useEffect(() => {
    if (!measuredRunId) return;
    let live = true;
    jobsApi
      .result(measuredRunId, false)
      .then((r) => {
        if (!live) return;
        setHeadline(r.verdict_label ?? null);
        setRange(effectRange(r.bundle?.items));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [measuredRunId]);

  const reset = () => {
    stopRef.current?.();
    dispatch({ type: "reset" });
  };

  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>{runCopy.title}</h1>
      <Stepper index={stepIndex(state.step)} />
      {state.step !== "run" && <LensCaption />}

      {state.step === "configure" && (
        <Card>
          <h2 className={styles.heading}>{runCopy.configure.heading}</h2>
          <dl className={styles.facts}>
            <div>
              <dt>{runCopy.configure.case}</dt>
              <dd>{caseId}</dd>
            </div>
            <div>
              <dt>{runCopy.configure.dataMode}</dt>
              <dd>
                <Chip tone="sim">{runCopy.configure.simulated}</Chip>
              </dd>
            </div>
            <div>
              <dt>{runCopy.configure.seed}</dt>
              <dd>{runCopy.configure.seedNote}</dd>
            </div>
            <div>
              <dt>{runCopy.configure.spec}</dt>
              <dd>Synthetic control, default specification</dd>
            </div>
          </dl>
          <div className={styles.field}>
            <label htmlFor="run-min-donors">{runCopy.configure.donors}</label>
            <input
              id="run-min-donors"
              name="min_donors"
              type="number"
              inputMode="numeric"
              min={2}
              step={1}
              placeholder="The case's own minimum"
              value={minDonorsText}
              onChange={(e) => setMinDonorsText(e.target.value)}
              aria-describedby="run-min-donors-hint"
              aria-invalid={minDonors === null}
            />
            <p id="run-min-donors-hint" className={styles.stamps}>
              {runCopy.configure.donorsHint}
            </p>
          </div>
          <Button onClick={start} loading={state.submitting} disabled={minDonors === null}>
            {state.submitting ? runCopy.configure.starting : runCopy.configure.start}
          </Button>
        </Card>
      )}

      {state.step === "run" && state.job && <Theatre job={state.job} cancelling={state.cancelling} onCancel={cancel} />}

      {state.step === "results" && state.outcome && (
        <OutcomeCard outcome={state.outcome} runId={state.runId} onRetry={reset} />
      )}

      {state.step === "results" && !state.outcome && (
        <Card>
          <h2 className={styles.heading}>{runCopy.results.heading}</h2>
          {state.job?.is_simulated && <Chip tone="sim">{runCopy.run.simulatedBadge}</Chip>}
          <p className={styles.stamps}>{runCopy.results.notLive}</p>
          {headline && (
            <p className={styles.headline}>
              {runCopy.results.headline}: {headline}
            </p>
          )}
          {range && (
            <RangeBar
              estimate={range.estimate}
              low={range.low}
              high={range.high}
              unit={range.unit}
              label={`Headline effect with its ${range.kind} interval`}
            />
          )}
          <Lens show="explorer">
            {state.job && stageDurationBars(state.job.stages).length > 0 && (
              <BarList items={stageDurationBars(state.job.stages)} label="Time taken by each stage" />
            )}
          </Lens>
          <Lens show="auditor">
            <p className={styles.stamps}>
              Run id <code>{state.runId}</code>
            </p>
          </Lens>
          <div className={styles.row}>
            <LinkButton href={evidenceLink}>{runCopy.results.evidence}</LinkButton>
            <LinkButton variant="secondary" href={overviewLink}>
              {runCopy.results.overview}
            </LinkButton>
            <Button variant="ghost" onClick={reset}>
              {runCopy.results.again}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
