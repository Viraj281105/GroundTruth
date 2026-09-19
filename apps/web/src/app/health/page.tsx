'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { getHealth } from '../../lib/api';
import { HealthResponse } from '../../lib/types';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Shield,
  Layers,
  FileCode2,
  AlertTriangle,
  ArrowLeft,
} from 'lucide-react';
import styles from './page.module.css';

export default function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadHealth() {
      setIsLoading(true);
      const data = await getHealth();
      setHealth(data);
      setIsLoading(false);
    }
    loadHealth();
  }, []);

  return (
    <div className="gt-container" style={{ paddingTop: '24px', paddingBottom: '60px' }}>
      <Link href="/" className={styles.backLink}>
        <ArrowLeft size={16} />
        <span>Back to Project Cases</span>
      </Link>

      <div className={styles.header}>
        <div className={styles.badgeRow}>
          <Badge tone="info" size="md" variant="subtle" icon={<Activity size={14} />}>
            SYSTEM HEALTH & CAPABILITY REPORT
          </Badge>
          <Badge tone="neutral" size="md" variant="outline">
            AST CONTRACT ENFORCEMENT ACTIVE
          </Badge>
        </div>

        <h1 className={styles.title}>Capability Matrix & Engine Liveness</h1>
        <p className={styles.subtitle}>
          Honest status reporting. The system reports what is implemented, what is planned, and what is deliberately not supported.
        </p>
      </div>

      {/* Honest Manifesto Alert */}
      <div className={styles.manifestoBox}>
        <div className={styles.manifestoIcon}>
          <AlertTriangle size={22} className={styles.alertIcon} />
        </div>
        <div className={styles.manifestoContent}>
          <strong className={styles.manifestoTitle}>Three Non-Negotiable Scientific Guardrails:</strong>
          <ul className={styles.manifestoList}>
            <li>
              <strong>NDVI is not carbon:</strong> Spectral indices cannot be converted to tonnes of CO2 without site-specific allometry and propagated error budgets.
            </li>
            <li>
              <strong>Observed change is not causal effect:</strong> Every estimate is conditional on its donor pool and identifying assumptions.
            </li>
            <li>
              <strong>Model divergence is not fraud:</strong> Divergence indicates a need for accredited field audit, not intent or wrongdoing.
            </li>
          </ul>
        </div>
      </div>

      {health && (
        <div className={styles.cardsGrid}>
          {/* Liveness & Versioning Card */}
          <Card variant="default">
            <CardHeader>
              <CardTitle>System & Contract Versions</CardTitle>
              <CardDescription>
                Formal versioning ensures the engine, platform, and frontend agree on evidence bundle schemas.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className={styles.metaList}>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>API Status:</span>
                  <Badge tone="positive" size="sm" variant="subtle">ONLINE (HEALTHY)</Badge>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Package Version:</span>
                  <span className={styles.metaValMono}>{health.version}</span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Contract Version:</span>
                  <span className={styles.metaValMono}>{health.contract_version}</span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Engine Version:</span>
                  <span className={styles.metaValMono}>{health.engine_version}</span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Registered Cases:</span>
                  <span className={styles.metaVal}>{health.cases_available} Projects</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Earth Observation Status */}
          <Card variant="default">
            <CardHeader>
              <CardTitle>Earth Observation Reducer Chain</CardTitle>
              <CardDescription>
                Satellite data access via Earth Engine and open archives.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className={styles.metaList}>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Observed Reduction:</span>
                  <Badge tone="caution" size="sm" variant="subtle">PLANNED FOR MVP</Badge>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Synthetic Provider:</span>
                  <Badge tone="positive" size="sm" variant="subtle">IMPLEMENTED</Badge>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Simulated Fallback Guard:</span>
                  <Badge tone="info" size="sm" variant="subtle">
                    REFUSES OBSERVED REQUESTS WITH 501
                  </Badge>
                </div>
              </div>
              <p className={styles.cardNote}>
                Requests for real observed data return HTTP 501 rather than silently serving simulated numbers.
              </p>
            </CardContent>
          </Card>

          {/* Engine Capabilities Table */}
          <div style={{ gridColumn: '1 / -1' }}>
            <Card variant="default">
              <CardHeader>
                <CardTitle>Analytical Engine Capabilities</CardTitle>
                <CardDescription>
                  Verified by automated AST boundary tests and recovery assertions.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className={styles.capabilitiesTableWrapper}>
                  <table className={styles.capabilitiesTable}>
                    <thead>
                      <tr>
                        <th>Capability</th>
                        <th>Owner</th>
                        <th>Status</th>
                        <th>Verification Method</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td><strong>Simplex-Constrained Synthetic Control</strong></td>
                        <td>Viraj</td>
                        <td><Badge tone="positive" size="sm">IMPLEMENTED</Badge></td>
                        <td>Hand-written FISTA solver in pure NumPy</td>
                      </tr>
                      <tr>
                        <td><strong>In-Space Placebo Permutation Suite</strong></td>
                        <td>Viraj</td>
                        <td><Badge tone="positive" size="sm">IMPLEMENTED</Badge></td>
                        <td>Permutation p-value with add-one correction</td>
                      </tr>
                      <tr>
                        <td><strong>Leave-One-Donor-Out Sensitivity</strong></td>
                        <td>Viraj</td>
                        <td><Badge tone="positive" size="sm">IMPLEMENTED</Badge></td>
                        <td>Sign stability and sensitivity envelope</td>
                      </tr>
                      <tr>
                        <td><strong>Difference-in-Differences Cross-Check</strong></td>
                        <td>Viraj</td>
                        <td><Badge tone="positive" size="sm">IMPLEMENTED</Badge></td>
                        <td>Pre-trend parallel trends screening diagnostic</td>
                      </tr>
                      <tr>
                        <td><strong>Evidence Assembly & Verdict Gate Chain</strong></td>
                        <td>Viraj</td>
                        <td><Badge tone="positive" size="sm">IMPLEMENTED</Badge></td>
                        <td>Immutable evidence bundle with mandatory provenance</td>
                      </tr>
                      <tr>
                        <td><strong>Numerical Grounding Verifier</strong></td>
                        <td>Bhumi</td>
                        <td><Badge tone="positive" size="sm">IMPLEMENTED</Badge></td>
                        <td>Adversarial test suite rejects ungrounded narratives</td>
                      </tr>
                      <tr>
                        <td><strong>Earth Engine S2/Landsat Reducer</strong></td>
                        <td>Bhumi / Viraj</td>
                        <td><Badge tone="caution" size="sm">PLANNED (MVP)</Badge></td>
                        <td>Requires Earth Engine client behind ObservationAccess port</td>
                      </tr>
                      <tr>
                        <td><strong>Biomass / Carbon Allometric Conversion</strong></td>
                        <td>Viraj</td>
                        <td><Badge tone="inconclusive" size="sm">PLANNED (STAGE 2)</Badge></td>
                        <td>Deferred rather than approximated with unpropagated error</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
