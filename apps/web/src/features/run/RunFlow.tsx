"use client";

import React, { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { Button, Card, Chip, LinkButton } from "../../components/ds";
import { ApiUnreachableError } from "../../lib/api";
import { createJobsApi, failureFrom, type JobView } from "../../lib/jobs";
import { watchJob } from "../../lib/jobs-stream";
import { runCopy } from "./copy";
import { initialState, reduce, stepIndex, STEP_ORDER, type Outcome } from "./machine";
import { Theatre } from "./Theatre";
import styles from "./run.module.css";

const jobsApi = createJobsApi();

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

function OutcomeCard({ outcome, caseId, onRetry }: { outcome: Outcome; caseId: string; onRetry: () => void }) {
  return (
    <Card className={styles.outcome} role="status">
      <h2>{outcome.title}</h2>
      <p>{outcome.reason}</p>
      <p className={styles.next}>{outcome.next}</p>
      <div className={styles.row}>
        <Button onClick={onRetry}>{runCopy.retry}</Button>
        <LinkButton variant="ghost" href={`/cases/${caseId}/method`}>
          Method
        </LinkButton>
      </div>
    </Card>
  );
}

export function RunFlow({ caseId }: { caseId: string }) {
  const [state, dispatch] = useReducer(reduce, initialState);
  const [headline, setHeadline] = useState<string | null>(null);
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => () => stopRef.current?.(), []);

  const watch = useCallback((runId: string) => {
    stopRef.current?.();
    stopRef.current = watchJob(runId, {
      onProgress: (job: JobView) => dispatch({ type: "progress", job }),
      onDone: (job: JobView) => dispatch({ type: "done", job }),
      onError: (err) =>
        dispatch({
          type: "submitFailed",
          unreachable: err instanceof ApiUnreachableError,
          reason: failureFrom(err).message,
        }),
    });
  }, []);

  const start = async () => {
    dispatch({ type: "start" });
    setHeadline(null);
    try {
      const sub = await jobsApi.submit({ case_id: caseId, synthetic: true });
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
      .then((r) => live && setHeadline(r.verdict_label ?? null))
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
          <Button onClick={start} loading={state.submitting}>
            {state.submitting ? runCopy.configure.starting : runCopy.configure.start}
          </Button>
        </Card>
      )}

      {state.step === "run" && state.job && <Theatre job={state.job} cancelling={state.cancelling} onCancel={cancel} />}

      {state.step === "results" && state.outcome && (
        <OutcomeCard outcome={state.outcome} caseId={caseId} onRetry={reset} />
      )}

      {state.step === "results" && !state.outcome && (
        <Card>
          <h2 className={styles.heading}>{runCopy.results.heading}</h2>
          {state.job?.is_simulated && <Chip tone="sim">{runCopy.run.simulatedBadge}</Chip>}
          {headline && (
            <p className={styles.headline}>
              {runCopy.results.headline}: {headline}
            </p>
          )}
          <div className={styles.row}>
            <LinkButton href={`/cases/${caseId}/evidence`}>{runCopy.results.evidence}</LinkButton>
            <LinkButton variant="secondary" href={`/cases/${caseId}`}>
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
