import React from 'react';
import { RefusalInfo } from '../../lib/api';
import { formatPeriods, isAlignmentDetail } from '../../lib/refusal';
import styles from './RefusalDetails.module.css';

/**
 * The structured part of a refusal: which engine code and stage refused, and
 * for an alignment refusal, which series are missing which periods. A refusal
 * is a legitimate outcome, so this is presented as information, not an error.
 */
export const RefusalDetails: React.FC<{ refusal: RefusalInfo }> = ({ refusal }) => {
  const alignment = isAlignmentDetail(refusal.detail) ? refusal.detail : null;
  return (
    <div className={styles.container}>
      {(refusal.code || refusal.stage) && (
        <dl className={styles.meta}>
          {refusal.code && (
            <div>
              <dt>Engine code</dt>
              <dd>{refusal.code}</dd>
            </div>
          )}
          {refusal.stage && (
            <div>
              <dt>Stage</dt>
              <dd>{refusal.stage}</dd>
            </div>
          )}
          {refusal.runId && (
            <div>
              <dt>Run</dt>
              <dd>{refusal.runId}</dd>
            </div>
          )}
        </dl>
      )}

      {alignment && (
        <div className={styles.alignment}>
          <p className={styles.text}>
            The analysis window is {alignment.window.pre_start}–{alignment.window.pre_end} before
            treatment and {alignment.window.post_start}–{alignment.window.post_end} after.{' '}
            {alignment.n_units_misaligned} series do not cover it, so the estimators were not run
            rather than fitted on a misaligned panel.
          </p>
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <caption className={styles.caption}>Series that do not cover the analysis window</caption>
              <thead>
                <tr>
                  <th scope="col">Region</th>
                  <th scope="col">Missing periods</th>
                  <th scope="col">Non-finite values</th>
                </tr>
              </thead>
              <tbody>
                {alignment.units.map((u) => (
                  <tr key={u.unit_id}>
                    <th scope="row">{u.unit_id}</th>
                    <td>{formatPeriods(u.missing_periods)}</td>
                    <td>{formatPeriods(u.non_finite_periods)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
