'use client';

import React, { useEffect, useRef, useState } from 'react';
import { formatBbox, weightOpacity, type BoundaryModel } from './map-model';
import styles from './map.module.css';

type MapLibre = any;

/**
 * maplibre-gl is an optional runtime dependency. `require` inside try/catch is
 * resolved by webpack as optional, so a missing install degrades to the text
 * fallback instead of failing the build.
 */
function loadMapLibre(): MapLibre | null {
  try {
    const mod = require('maplibre-gl');
    return mod?.default ?? mod;
  } catch {
    return null;
  }
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || 'currentColor';
}

function paintColors() {
  return {
    background: token('--surface-sunken'),
    fill: token('--accent'),
    line: token('--accent-strong'),
    donor: token('--series-synthetic'),
  };
}

export default function MapCanvas({ model }: { model: BoundaryModel }) {
  const host = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const maplibre = loadMapLibre();
    if (!maplibre || !host.current) {
      setFailed(true);
      return;
    }
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const maxW = Math.max(0, ...model.donorWeights.map((d) => d.weight));
    const opacityByIndex = new Map(model.donorWeights.map((d) => [d.index, weightOpacity(d.weight, maxW)]));
    const data = {
      type: 'FeatureCollection',
      features: model.data.features.map((f, i) => ({
        ...f,
        properties: { ...(f.properties ?? {}), _op: opacityByIndex.get(i) ?? 0, _donor: opacityByIndex.has(i) },
      })),
    };
    const c = paintColors();
    let map: any;
    try {
      map = new maplibre.Map({
        container: host.current,
        style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': c.background } }] },
        bounds: model.bbox,
        fitBoundsOptions: { padding: 24, animate: false },
        attributionControl: false,
        interactive: true,
        cooperativeGestures: true,
      });
    } catch {
      setFailed(true);
      return;
    }
    map.on('load', () => {
      map.addSource('boundary', { type: 'geojson', data });
      map.addLayer({ id: 'boundary-fill', type: 'fill', source: 'boundary', filter: ['==', ['get', '_donor'], false], paint: { 'fill-color': c.fill, 'fill-opacity': 0.22 } });
      map.addLayer({ id: 'donor-fill', type: 'fill', source: 'boundary', filter: ['==', ['get', '_donor'], true], paint: { 'fill-color': c.donor, 'fill-opacity': ['get', '_op'] } });
      map.addLayer({ id: 'boundary-line', type: 'line', source: 'boundary', paint: { 'line-color': c.line, 'line-width': 2 } });
      map.addLayer({ id: 'boundary-pt', type: 'circle', source: 'boundary', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-color': c.line, 'circle-radius': 5 } });
      if (reduceMotion) map.setPadding({ top: 0, bottom: 0, left: 0, right: 0 });
    });
    const recolor = () => {
      if (!map.getLayer('boundary-fill')) return;
      const n = paintColors();
      map.setPaintProperty('bg', 'background-color', n.background);
      map.setPaintProperty('boundary-fill', 'fill-color', n.fill);
      map.setPaintProperty('donor-fill', 'fill-color', n.donor);
      map.setPaintProperty('boundary-line', 'line-color', n.line);
      map.setPaintProperty('boundary-pt', 'circle-color', n.line);
    };
    const observer = new MutationObserver(recolor);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] });
    return () => {
      observer.disconnect();
      map.remove();
    };
  }, [model]);

  if (failed) return <MapFallback model={model} />;
  return (
    <div className={styles.mapWrap}>
      <div
        ref={host}
        className={styles.map}
        role="img"
        aria-label={`Project boundary map. ${formatBbox(model.bbox)}.`}
      />
    </div>
  );
}

export function MapFallback({ model }: { model: BoundaryModel }) {
  return (
    <dl className={styles.fallback}>
      <div>
        <dt>Map unavailable</dt>
        <dd>The map library did not load. The boundary the API returned is summarised here instead.</dd>
      </div>
      <div>
        <dt>Bounding box</dt>
        <dd>{formatBbox(model.bbox)}</dd>
      </div>
      <div>
        <dt>Centre</dt>
        <dd>
          {model.centroid[1].toFixed(4)}, {model.centroid[0].toFixed(4)}
        </dd>
      </div>
      <div>
        <dt>Features</dt>
        <dd>{model.data.features.length}</dd>
      </div>
    </dl>
  );
}
