'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { API_BASE_URL } from '../../../lib/api';
import { Skeleton } from '../../../components/ds';
import { loadBoundary, type BoundaryResult } from './map-model';
import styles from './map.module.css';

const MapCanvas = dynamic(() => import('./MapCanvas'), {
  ssr: false,
  loading: () => <Skeleton height="20rem" radius="var(--radius-lg)" />,
});

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
