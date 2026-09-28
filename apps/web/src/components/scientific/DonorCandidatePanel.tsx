import React from 'react';
import {
  DONOR_EXCLUSION_CATEGORIES,
  DonorCandidateSummary,
  resultStateLabel,
  resultStateTone,
} from '../../lib/types';
import { formatMeasurement } from '../../lib/formatters';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { MetricDisplay } from '../ui/MetricDisplay';
import { Info } from 'lucide-react';
import styles from './DonorCandidatePanel.module.css';

export interface DonorCandidatePanelProps {
  summary: DonorCandidateSummary;
  className?: string;
}

const EXCLUSION_CATEGORY_LABEL: Record<string, string> = {
  empty_after_mask: 'Empty After Mask',
  ecoregion_share: 'Ecoregion Share',
  area_floor: 'Area Floor',
  area_band: 'Area Band',
  leakage_belt: 'Leakage Belt',
  carbon_project: 'Carbon Project',
};

const NOT_MEASURED = 'Not measured';

/** A table/metric cell value, styled distinctly when it is an explicit absence. */
function Measurement({ value }: { value: string }) {
  return <span className={value === NOT_MEASURED ? styles.notMeasured : undefined}>{value}</span>;
}

/**
 * Smallest useful view of ADR-011 donor-candidate generation for one case.
 *
 * Every measurement is nullable in `DonorCandidateSummary`, and every field
 * here renders "Not measured" for a `null`, never a `0` or a blank — see
 * `formatMeasurement`. `0` is only ever shown for a value ADR-011's pipeline
 * actually produced.
 */
export const DonorCandidatePanel: React.FC<DonorCandidatePanelProps> = ({
  summary,
  className = '',
}) => {
  return (
    <Card variant="default" className={className}>
      <CardHeader>
        <div className={styles.headerRow}>
          <CardTitle>Donor Candidate Generation</CardTitle>
          <Badge tone={resultStateTone(summary.resultState)} size="sm" variant="outline">
            RUN: {resultStateLabel(summary.resultState)}
          </Badge>
        </div>
        <CardDescription>
          {summary.caseName} · Unit of analysis per{' '}
          <span className={styles.adrRef}>
            ADR-011: The unit of analysis is a masked administrative district
          </span>
        </CardDescription>
      </CardHeader>

      <CardContent>
        <div className={`gt-grid-3 ${styles.metricsGrid}`}>
          <MetricDisplay
            label="Treated Eligible Area"
            value={formatMeasurement(summary.treatedEligibleAreaKm2, 'km²')}
            size="sm"
          />
          <MetricDisplay
            label="Eligible Candidates"
            value={formatMeasurement(summary.candidateCount)}
            size="sm"
          />
          <MetricDisplay
            label="Admitted Donors"
            value={formatMeasurement(summary.admittedDonorCount)}
            size="sm"
          />
        </div>

        {/* Search-region ladder */}
        <div className={styles.section}>
          <h4 className={styles.sectionHeading}>
            Search-Region Ladder
            {summary.rungUsed !== null && (
              <Badge tone="info" size="sm" variant="subtle">
                RUNG {summary.rungUsed} USED
              </Badge>
            )}
          </h4>

          {summary.rungs.length === 0 ? (
            <div className={styles.emptyNotice}>
              <Info size={15} className={styles.emptyNoticeIcon} />
              <p className={styles.emptyNoticeText}>
                No ladder climb recorded. ADR-011 candidate generation has not run for this case —
                the Earth Engine masking chain is not yet implemented, so nothing has been measured.
              </p>
            </div>
          ) : (
            <div className={styles.tableWrapper}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Rung</th>
                    <th>Search Region</th>
                    <th className={styles.numeric}>Screened</th>
                    <th className={styles.numeric}>Eligible</th>
                    <th className={styles.numeric}>Admitted</th>
                    <th>Stopping Rule</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.rungs.map((rung) => (
                    <tr key={rung.rung}>
                      <td>{rung.rung}</td>
                      <td>{rung.description}</td>
                      <td className={styles.numeric}>
                        <Measurement value={formatMeasurement(rung.districtsScreened)} />
                      </td>
                      <td className={styles.numeric}>
                        <Measurement value={formatMeasurement(rung.eligibleCandidates)} />
                      </td>
                      <td className={styles.numeric}>
                        <Measurement value={formatMeasurement(rung.admittedDonors)} />
                      </td>
                      <td>
                        {rung.satisfiedStoppingRule === null ? (
                          <Measurement value={NOT_MEASURED} />
                        ) : (
                          <Badge
                            tone={rung.satisfiedStoppingRule ? 'positive' : 'neutral'}
                            size="sm"
                            variant="subtle"
                          >
                            {rung.satisfiedStoppingRule ? 'SATISFIED' : 'NOT SATISFIED'}
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Exclusion categories */}
        <div className={styles.section}>
          <h4 className={styles.sectionHeading}>Exclusion Categories</h4>
          <div className="gt-grid-3">
            {DONOR_EXCLUSION_CATEGORIES.map((category) => (
              <MetricDisplay
                key={category}
                label={EXCLUSION_CATEGORY_LABEL[category] || category}
                value={formatMeasurement(summary.exclusionsByCategory?.[category] ?? null)}
                size="sm"
              />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
