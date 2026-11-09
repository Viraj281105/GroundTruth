'use client';

import React, { useEffect, useRef, useState } from 'react';
import { basemapStyle, fitBoundsFor, fitBoundsForAll, settleBoundaries } from './geo';
import styles from './ProjectMap.module.css';

export interface ProjectMapProps {
  /** Optional when `regionalBoundaries` is non-empty: then each boundary fails soft on its own. */
  boundaryUrl?: string;
  donorsUrl?: string;
  regionalBoundaries?: string[];
  height?: number | string;
}

type Status =
  | { kind: 'loading' }
  | { kind: 'ready' }
  | { kind: 'error'; message: string };

const UNAVAILABLE = 'Boundary not available to your organization';
const NETWORK = 'Map data could not be loaded';

function loadMapLibre(): any | null {
  try {
    const mod = require('maplibre-gl');
    return mod?.default ?? mod;
  } catch {
    return null;
  }
}

async function fetchGeoJson(url: string): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(url, { credentials: 'include' });
  } catch {
    throw new Error(NETWORK);
  }
  if ([401, 403, 404].includes(res.status)) throw new Error(UNAVAILABLE);
  if (!res.ok) throw new Error(NETWORK);
  try {
    return await res.json();
  } catch {
    throw new Error(NETWORK);
  }
}

function token(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export default function ProjectMap({ boundaryUrl, donorsUrl, regionalBoundaries, height = '20rem' }: ProjectMapProps) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>({ kind: 'loading' });
  const [plain, setPlain] = useState(false);
  const [skipped, setSkipped] = useState(0);
  const regionalKey = (regionalBoundaries ?? []).join('|');

  useEffect(() => {
    let cancelled = false;
    let map: any = null;
    setStatus({ kind: 'loading' });
    setPlain(false);
    setSkipped(0);

    (async () => {
      try {
        let boundary: unknown = null;
        let multi: unknown[] = [];
        let failed = 0;
        if (boundaryUrl) {
          boundary = await fetchGeoJson(boundaryUrl);
        } else {
          const settled = settleBoundaries(await Promise.all((regionalBoundaries ?? []).map((u) => fetchGeoJson(u).catch(() => null))));
          if (settled.ok.length === 0) throw new Error(UNAVAILABLE);
          multi = settled.ok;
          failed = settled.failed;
        }
        // Donors and regional layers are optional: failure never hides the boundary.
        const donors = donorsUrl ? await fetchGeoJson(donorsUrl).catch(() => null) : null;
        const regionals = boundaryUrl
          ? await Promise.all((regionalBoundaries ?? []).map((u) => fetchGeoJson(u).catch(() => null)))
          : [];
        if (cancelled) return;
        let bounds: [[number, number], [number, number]];
        try {
          bounds = boundaryUrl ? fitBoundsFor(boundary) : fitBoundsForAll(multi);
        } catch (err) {
          const msg = err instanceof Error && /no geometry/i.test(err.message)
            ? 'The boundary file contains no geometry'
            : NETWORK;
          setStatus({ kind: 'error', message: msg });
          return;
        }
        setSkipped(failed);
        setStatus({ kind: 'ready' });

        const maplibre = loadMapLibre();
        if (!maplibre || !host.current) {
          setPlain(true);
          return;
        }
        try {
          map = new maplibre.Map({
            container: host.current,
            style: basemapStyle(),
            bounds,
            fitBoundsOptions: { padding: 24, animate: false },
            attributionControl: false,
            cooperativeGestures: true,
          });
          map.addControl(new maplibre.AttributionControl({ compact: false }), 'bottom-right');
        } catch {
          setPlain(true);
          return;
        }
        const accent = token('--accent', '#2f6f4f');
        const accentStrong = token('--accent-strong', '#1f4d36');
        const donorColor = token('--map-donor', token('--text-muted', '#5b6470'));
        map.on('load', () => {
          regionals.forEach((g, i) => {
            if (!g) return;
            map.addSource(`regional-${i}`, { type: 'geojson', data: g });
            map.addLayer({ id: `regional-${i}-line`, type: 'line', source: `regional-${i}`, paint: { 'line-color': '#6b7280', 'line-width': 1, 'line-dasharray': [2, 2] } });
          });
          if (donors) {
            map.addSource('donors', { type: 'geojson', data: donors });
            map.addLayer({ id: 'donors-fill', type: 'fill', source: 'donors', paint: { 'fill-color': donorColor, 'fill-opacity': 0.3 } });
            map.addLayer({ id: 'donors-line', type: 'line', source: 'donors', paint: { 'line-color': donorColor, 'line-width': 1.5, 'line-dasharray': [3, 2] } });
          }
          const drawn = boundaryUrl ? [boundary] : multi;
          drawn.forEach((g, i) => {
            map.addSource(`boundary-${i}`, { type: 'geojson', data: g });
            map.addLayer({ id: `boundary-${i}-fill`, type: 'fill', source: `boundary-${i}`, paint: { 'fill-color': accent, 'fill-opacity': 0.22 } });
            map.addLayer({ id: `boundary-${i}-line`, type: 'line', source: `boundary-${i}`, paint: { 'line-color': accentStrong, 'line-width': 2 } });
          });
        });
      } catch (e) {
        if (!cancelled) setStatus({ kind: 'error', message: e instanceof Error ? e.message : NETWORK });
      }
    })();

    return () => {
      cancelled = true;
      if (map) map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundaryUrl, donorsUrl, regionalKey]);

  return (
    <div className={styles.wrap} style={{ height }}>
      <div ref={host} className={styles.map} role="group" aria-label="Project boundary map" hidden={plain || status.kind === 'error'} />
      {status.kind === 'ready' && plain && (
        <div className={styles.state} role="status">Map unavailable in this browser</div>
      )}
      {status.kind === 'loading' && <div className={styles.state} aria-busy="true">Loading map…</div>}
      {status.kind === 'error' && (
        <div className={styles.state} role="alert">
          {status.message}
        </div>
      )}
      {status.kind === 'ready' && skipped > 0 && (
        <div className={styles.legend} role="note">{skipped} {skipped === 1 ? 'boundary' : 'boundaries'} unavailable to your organization</div>
      )}
      {status.kind === 'ready' && donorsUrl && !plain && <div className={styles.legend}>Dashed: donor regions</div>}
    </div>
  );
}
