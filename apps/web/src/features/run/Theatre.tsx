"use client";

import React, { useEffect, useState } from "react";
import { Button, Card, Chip } from "../../components/ds";
import type { JobView } from "../../lib/jobs";
import { runCopy } from "./copy";
import { formatElapsed, stageLabel } from "./machine";
import styles from "./run.module.css";

const MARK: Record<string, string> = { done: "✓", failed: "!", skipped: "–" };

/** The live stage pipeline. Stage names, states and durations are exactly what the API reported. */
export function Theatre({
  job,
  cancelling,
  onCancel,
}: {
  job: JobView;
  cancelling: boolean;
  onCancel: () => void;
}) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <Card aria-live="polite">
      <div className={styles.row}>
        <h2 className={styles.heading}>{runCopy.run.heading}</h2>
        {job.is_simulated && <Chip tone="sim">{runCopy.run.simulatedBadge}</Chip>}
        <span className={styles.elapsed}>
          {runCopy.run.elapsed} {formatElapsed(now - start)}
        </span>
      </div>
      {job.stages.length === 0 ? (
        <p>{runCopy.run.waiting}</p>
      ) : (
        <ol className={styles.pipeline}>
          {job.stages.map((s, i) => {
            const cls =
              s.state === "active"
                ? styles.stageActive
                : s.state === "done"
                  ? styles.stageDone
                  : s.state === "failed"
                    ? styles.stageFailed
                    : "";
            return (
              <li key={s.name} className={`${styles.stage} ${cls}`} aria-current={s.state === "active" ? "step" : undefined}>
                <span className={styles.marker} aria-hidden="true">
                  {MARK[s.state] ?? ""}
                </span>
                <span className={styles.stageText}>
                  <span className={styles.stageName}>
                    {i + 1}. {stageLabel(s.name, s.label)}
                  </span>
                  <span className={styles.stageMeta}>{s.state}</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
      <Button variant="secondary" onClick={onCancel} disabled={cancelling} loading={cancelling}>
        {cancelling ? runCopy.run.cancelling : runCopy.run.cancel}
      </Button>
    </Card>
  );
}
