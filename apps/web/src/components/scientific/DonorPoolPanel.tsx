'use client';

import React, { useState } from 'react';
import { Evidence } from '../../lib/types';
import { Candidate, deriveDonorPool, groupExclusions } from '../../lib/donor-pool';
import { findEvidence, numberValue, sig } from '../../lib/evidence';
import { DiagnosticPanel } from './DiagnosticPanel';
import styles from './DonorPoolPanel.module.css';

export interface DonorPoolPanelProps {
  items: Evidence[];
  /**
   * Per-candidate matching outcomes. Only the generated fixture has them
   * today; `undefined` on a real API response.
   */
  candidates?: Candidate[];
  onSelectEvidence: (item: Evidence) => void;
}

const PREVIEW = 5;

/**
 * Donor pool from evidence, plus every excluded candidate grouped by the rule
 * that removed it, so a reviewer can challenge the pool rather than the
 * estimate.
 */
export const DonorPoolPanel: React.FC<DonorPoolPanelProps> = ({ items, candidates, onSelectEvidence }) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const groups = candidates ? groupExclusions(candidates) : [];
  const nExcluded = numberValue(findEvidence(items, 'matching.n_candidates_excluded'));

  return (
    <div className={styles.container}>
      <DiagnosticPanel
        id="donor-pool"
        title="Donor pool & matching"
        description="Which comparison regions the counterfactual is built from, and how closely they match the project on covariates."
        groups={deriveDonorPool(items)}
        columns={2}
        onSelectEvidence={onSelectEvidence}
      />

      <section className={styles.exclusions} aria-labelledby="donor-exclusions-title">
        <h4 id="donor-exclusions-title" className={styles.title}>
          Excluded candidates{nExcluded !== undefined ? ` (${nExcluded})` : ''}
        </h4>
        {!candidates ? (
          <p className={styles.note}>
            {nExcluded !== undefined ? `${nExcluded} candidate regions were excluded. ` : ''}
            Per-candidate reasons are recorded by the engine but not yet returned by the API, so they
            cannot be listed here.
          </p>
        ) : groups.length === 0 ? (
          <p className={styles.note}>No candidate region was excluded.</p>
        ) : (
          <>
            <p className={styles.note}>
              Every exclusion carries the rule that produced it. Distance is the standardised covariate
              distance to the project (lower is closer).
            </p>
            {groups.map((g) => {
              const open = expanded[g.rule] ?? false;
              const shown: Candidate[] = open ? g.candidates : g.candidates.slice(0, PREVIEW);
              const tableId = `exclusions-${g.rule}`;
              return (
                <div key={g.rule} className={styles.group}>
                  <h5 className={styles.groupTitle}>
                    {g.label} <span className={styles.count}>({g.candidates.length})</span>
                  </h5>
                  <p className={styles.groupDesc}>{g.description}</p>
                  <div className={styles.tableWrapper}>
                    <table className={styles.table} id={tableId}>
                      <thead>
                        <tr>
                          <th scope="col">Region</th>
                          <th scope="col">Distance</th>
                          <th scope="col">Engine reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.map((c) => (
                          <tr key={c.unit_id}>
                            <th scope="row">{c.unit_id}</th>
                            <td>{sig(c.distance)} (standardised)</td>
                            <td>{c.exclusion_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {g.candidates.length > PREVIEW && (
                    <button
                      type="button"
                      className={styles.toggle}
                      aria-expanded={open}
                      aria-controls={tableId}
                      onClick={() => setExpanded((s) => ({ ...s, [g.rule]: !open }))}
                    >
                      {open ? 'Show fewer' : `Show all ${g.candidates.length}`}
                    </button>
                  )}
                </div>
              );
            })}
          </>
        )}
      </section>
    </div>
  );
};
