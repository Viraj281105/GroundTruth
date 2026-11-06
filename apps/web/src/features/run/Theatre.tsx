"use client";

import React, { useEffect, useState } from "react";
import { Button, Card, Chip } from "../../components/ds";
import { BarList } from "../../components/charts";
import { Lens } from "../../lib/lens";
import { LensCaption } from "../case/overview/LensCaption";
import { stageDurationBars } from "./durations";
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

  const bars = stageDurationBars(job.stages);
  return (
    <Card aria-live="polite">
      <LensCaption />
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
      <Lens show="explorer">
        {bars.length > 0 && (
          <div className={styles.durations}>
            <h3 className={styles.heading}>Time per stage</h3>
            <BarList items={bars} label="Time taken by each finished stage" />
          </div>
        )}
      </Lens>
      <Lens show="auditor">
        <ul className={styles.stamps}>
          {job.stages.map((s) => (
            <li key={s.name}>
              <code>{s.name}</code> {s.state}
              {s.started_at ? `, started ${s.started_at}` : ""}
              {s.finished_at ? `, finished ${s.finished_at}` : ""}
            </li>
          ))}
        </ul>
      </Lens>
      <Button variant="secondary" onClick={onCancel} disabled={cancelling} loading={cancelling}>
        {cancelling ? runCopy.run.cancelling : runCopy.run.cancel}
      </Button>
    </Card>
  );
}
