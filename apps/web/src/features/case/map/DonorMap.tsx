'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { API_BASE_URL } from '../../../lib/api';
import { Skeleton } from '../../../components/ds';
import { formatBbox, loadBoundary, type BoundaryModel, type BoundaryResult } from './map-model';
import { bboxRect } from '../evidence/viz-model';
import vz from '../evidence/viz.module.css';
import styles from './map.module.css';

const MapCanvas = dynamic(() => import('./MapCanvas'), {
  ssr: false,
  loading: () => <Skeleton height="20rem" radius="var(--radius-lg)" />,
});

/** The project's bounding box on a lat/lon grid; drawn from the boundary file only. */
function ExtentCard({ model }: { model: BoundaryModel }) {
  const W = 320;
  const H = 180;
  const r = bboxRect(model.bbox);
  const [fw, fs, fe, fn] = r.frame;
  const gx = [0.25, 0.5, 0.75];
  return (
    <div className={vz.card}>
      <h3 className={vz.cardTitle}>Project extent</h3>
      <svg className={vz.mapSvg} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Project bounding box, ${formatBbox(model.bbox)}`}>
        <rect x="0.5" y="0.5" width={W - 1} height={H - 1} fill="none" className={vz.mapGrid} />
        {gx.map((f) => (
          <g key={f}>
            <line x1={f * W} x2={f * W} y1="0" y2={H} className={vz.mapGrid} />
            <line x1="0" x2={W} y1={f * H} y2={f * H} className={vz.mapGrid} />
            <text x={f * W + 3} y={H - 4} className={vz.mapText}>{(fw + f * (fe - fw)).toFixed(2)}°</text>
            <text x="3" y={f * H - 3} className={vz.mapText}>{(fn - f * (fn - fs)).toFixed(2)}°</text>
          </g>
        ))}
        <rect x={r.x * W} y={r.y * H} width={Math.max(r.w * W, 3)} height={Math.max(r.h * H, 3)} className={vz.mapRect} />
        <circle cx={((model.centroid[0] - fw) / (fe - fw)) * W} cy={((fn - model.centroid[1]) / (fn - fs)) * H} r="3.5" className={vz.mapDot} />
        <text x={Math.min(r.x * W + r.w * W + 6, W - 96)} y={r.y * H + 12} className={vz.mapLabel}>
          {model.centroid[1].toFixed(3)}°, {model.centroid[0].toFixed(3)}°
        </text>
      </svg>
      <p className={vz.cardNote}>{formatBbox(model.bbox)}. Centroid labelled; no donor geometry is drawn here.</p>
    </div>
  );
}

export function DonorMapView({ result }: { result: BoundaryResult | null }) {
  if (result === null) return <Skeleton height="20rem" radius="var(--radius-lg)" />;
  if (result.kind === 'error') {
    return (
      <p role="alert" className={styles.error}>
        {result.message}
      </p>
    );
  }
  if (result.kind === 'empty') {
    return (
      <p className={styles.empty}>
        {result.reason === 'not-found'
          ? 'No project boundary has been published for this case, so there is no map to draw.'
          : 'The boundary file contains no geometry, so there is no map to draw.'}
      </p>
    );
  }
  const { model } = result;
  return (
    <figure className={styles.figure}>
      <ExtentCard model={model} />
      <MapCanvas model={model} />
      <figcaption className={styles.caption}>
        {model.donorWeights.length > 0
          ? `Donor regions are shaded by their reported weight (${model.donorWeights.length} regions).`
          : 'Only the project boundary is drawn. Donor regions are not shaded because the data holds no donor geometry; donor weights are listed above.'}
      </figcaption>
    </figure>
  );
}

export function DonorMap({ caseId }: { caseId: string }) {
  const [result, setResult] = useState<BoundaryResult | null>(null);
  useEffect(() => {
    let cancelled = false;
    setResult(null);
    loadBoundary(API_BASE_URL, caseId).then((r) => {
      if (!cancelled) setResult(r);
    });
    return () => {
      cancelled = true;
    };
  }, [caseId]);
  return <DonorMapView result={result} />;
}
