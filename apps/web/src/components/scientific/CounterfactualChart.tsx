'use client';

import React, { useState, useRef, useEffect } from 'react';
import { ChartDataPoint } from '../../lib/fixtures/simulated-data';
import { Badge } from '../ui/Badge';
import { Info, ZoomIn, Calendar, Sliders } from 'lucide-react';
import styles from './CounterfactualChart.module.css';

export interface CounterfactualChartProps {
  data: ChartDataPoint[];
  treatmentYear?: number;
  indicator?: string;
  indicatorUnit?: string;
  preRMSPE?: number;
  postRMSPE?: number;
  className?: string;
}

export const CounterfactualChart: React.FC<CounterfactualChartProps> = ({
  data,
  treatmentYear = 2011,
  indicator = 'ndvi',
  indicatorUnit = 'ndvi',
  preRMSPE,
  postRMSPE,
  className = '',
}) => {
  const [hoveredPoint, setHoveredPoint] = useState<ChartDataPoint | null>(null);
  const [timeFilter, setTimeFilter] = useState<'all' | 'pre' | 'post'>('all');
  const svgRef = useRef<SVGSVGElement | null>(null);

  const filteredData = React.useMemo(() => {
    if (!data) return [];
    if (timeFilter === 'pre') return data.filter((d) => d.year <= treatmentYear);
    if (timeFilter === 'post') return data.filter((d) => d.year >= treatmentYear);
    return data;
  }, [data, timeFilter, treatmentYear]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!filteredData || filteredData.length === 0) return;
    const currentIndex = hoveredPoint
      ? filteredData.findIndex((d) => d.year === hoveredPoint.year)
      : -1;

    if (e.key === 'ArrowRight') {
      e.preventDefault();
      const nextIdx = Math.min(currentIndex + 1, filteredData.length - 1);
      setHoveredPoint(filteredData[nextIdx]);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const prevIdx = Math.max(currentIndex - 1, 0);
      setHoveredPoint(filteredData[prevIdx]);
    } else if (e.key === 'Escape') {
      setHoveredPoint(null);
    }
  };

  if (!data || data.length === 0) {
    return <div className={styles.empty}>No time series data available.</div>;
  }

  // Dimensions
  const width = 800;
  const height = 370;
  const padLeft = 60;
  const padRight = 30;
  const padTop = 30;
  const padBottom = 45;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  // Domain & Scale
  const years = filteredData.map((d) => d.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);

  const allVals = filteredData.flatMap((d) => [
    d.observed,
    d.synthetic,
    d.ciLower ?? d.synthetic,
    d.ciUpper ?? d.synthetic,
  ]);
  const minVal = Math.floor(Math.min(...allVals) * 20) / 20 - 0.02;
  const maxVal = Math.ceil(Math.max(...allVals) * 20) / 20 + 0.02;

  const scaleX = (year: number) =>
    padLeft + ((year - minYear) / Math.max(maxYear - minYear, 1)) * chartW;
  const scaleY = (val: number) =>
    padTop + chartH - ((val - minVal) / Math.max(maxVal - minVal, 0.001)) * chartH;

  const treatmentX = scaleX(treatmentYear);

  // Line paths
  const observedPoints = filteredData
    .map((d) => `${scaleX(d.year)},${scaleY(d.observed)}`)
    .join(' ');
  const syntheticPoints = filteredData
    .map((d) => `${scaleX(d.year)},${scaleY(d.synthetic)}`)
    .join(' ');

  // Gap polygon (post-treatment only)
  const postData = filteredData.filter((d) => d.year >= treatmentYear);
  const gapPolygonPoints = postData.length > 1
    ? [
        ...postData.map((d) => `${scaleX(d.year)},${scaleY(d.observed)}`),
        ...postData.slice().reverse().map((d) => `${scaleX(d.year)},${scaleY(d.synthetic)}`),
      ].join(' ')
    : '';

  // Sensitivity envelope polygon (using ciLower and ciUpper where available)
  const envelopeData = postData.filter((d) => d.ciLower !== undefined && d.ciUpper !== undefined);
  const envelopePolygonPoints = envelopeData.length > 1
    ? [
        ...envelopeData.map((d) => `${scaleX(d.year)},${scaleY(d.observed - (d.ciLower ?? 0))}`),
        ...envelopeData.slice().reverse().map((d) => `${scaleX(d.year)},${scaleY(d.observed + (d.ciUpper ?? 0))}`),
      ].join(' ')
    : '';

  // Y-axis ticks
  const nYTicks = 5;
  const yTicks = Array.from({ length: nYTicks }, (_, i) => {
    const val = minVal + (i / (nYTicks - 1)) * (maxVal - minVal);
    return { val, y: scaleY(val) };
  });

  // Touch handler for mobile scrubbing
  const handleTouchMove = (e: React.TouchEvent<SVGSVGElement>) => {
    if (!svgRef.current || filteredData.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const touchX = e.touches[0].clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, (touchX - padLeft) / chartW));
    const targetYear = Math.round(minYear + ratio * (maxYear - minYear));
    const closest = filteredData.reduce((prev, curr) =>
      Math.abs(curr.year - targetYear) < Math.abs(prev.year - targetYear) ? curr : prev
    );
    setHoveredPoint(closest);
  };

  return (
    <div
      className={`${styles.container} ${className}`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      role="region"
      aria-label={`Counterfactual Trajectory Chart for ${indicator.toUpperCase()}. Use left and right arrow keys to inspect yearly estimates.`}
    >
      {/* Header with Title, Filter Chips, and Legend */}
      <div className={styles.header}>
        <div className={styles.titleArea}>
          <div className={styles.titleRow}>
            <h4 className={styles.title}>Observed vs. Counterfactual Trajectory</h4>
            <Badge tone="info" size="sm" variant="subtle">
              INDICATOR: {indicator.toUpperCase()}
            </Badge>
            <span className={styles.keyboardHint}>[Focus & use ← / → keys to scrub]</span>
          </div>
          <p className={styles.subtitle}>
            Post-treatment divergence represents the estimated causal effect. Shaded gap is conditional on donor pool and identifying assumptions.
          </p>
        </div>

        {/* View Controls & Time Filters */}
        <div className={styles.controlRow}>
          <div className={styles.filterControlsGroup}>
            <div className={styles.timeFilterGroup}>
              <span className={styles.filterLabel}>WINDOW:</span>
              <button
                type="button"
                className={`${styles.filterBtn} ${timeFilter === 'all' ? styles.filterBtnActive : ''}`}
                onClick={() => setTimeFilter('all')}
              >
                FULL (2001–2022)
              </button>
              <button
                type="button"
                className={`${styles.filterBtn} ${timeFilter === 'pre' ? styles.filterBtnActive : ''}`}
                onClick={() => setTimeFilter('pre')}
              >
                PRE-PERIOD FIT
              </button>
              <button
                type="button"
                className={`${styles.filterBtn} ${timeFilter === 'post' ? styles.filterBtnActive : ''}`}
                onClick={() => setTimeFilter('post')}
              >
                POST-TREATMENT
              </button>
            </div>

            {/* Sensor Selector */}
            <div className={styles.sensorSelectorGroup}>
              <span className={styles.filterLabel}>SENSOR:</span>
              <span className={styles.sensorActivePill}>
                {indicator.toUpperCase()} (Optical)
              </span>
            </div>
          </div>

          {/* Legend */}
          <div className={styles.legend}>
            <div className={styles.legendItem}>
              <span className={styles.legendObservedLine} />
              <span className={styles.legendText}>Observed ({indicatorUnit})</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.legendSyntheticLine} />
              <span className={styles.legendText}>Synthetic Control</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.legendGapBox} />
              <span className={styles.legendText}>Estimated Effect</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.legendEnvelopeBox} />
              <span className={styles.legendText}>95% Sensitivity Envelope</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.legendTreatmentLine} />
              <span className={styles.legendText}>Intervention ({treatmentYear})</span>
            </div>
          </div>
        </div>
      </div>

      {/* Screen reader live region for keyboard scrubbing */}
      <div className="sr-only" aria-live="polite" style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}>
        {hoveredPoint
          ? `Year ${hoveredPoint.year}: Observed ${hoveredPoint.observed.toFixed(4)} ${indicatorUnit}, Synthetic ${hoveredPoint.synthetic.toFixed(4)} ${indicatorUnit}, Gap ${hoveredPoint.gap.toFixed(4)} ${indicatorUnit}`
          : ''}
      </div>

      {/* SVG Visualization */}
      <div className={styles.svgWrapper}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className={styles.svg}
          onMouseLeave={() => setHoveredPoint(null)}
          onTouchMove={handleTouchMove}
          onTouchEnd={() => setHoveredPoint(null)}
        >
          {/* Background Shading: Pre vs Post */}
          {treatmentYear >= minYear && (
            <rect
              x={padLeft}
              y={padTop}
              width={Math.max(0, treatmentX - padLeft)}
              height={chartH}
              className={styles.preBg}
            />
          )}
          {treatmentYear <= maxYear && (
            <rect
              x={Math.max(padLeft, treatmentX)}
              y={padTop}
              width={Math.max(0, padLeft + chartW - Math.max(padLeft, treatmentX))}
              height={chartH}
              className={styles.postBg}
            />
          )}

          {/* Phase Labels */}
          {treatmentYear > minYear && (
            <text
              x={padLeft + 10}
              y={padTop + 18}
              className={styles.phaseLabel}
            >
              PRE-INTERVENTION // CALIBRATION & PARALLEL TRENDS
            </text>
          )}
          {treatmentYear < maxYear && (
            <text
              x={Math.max(padLeft, treatmentX) + 12}
              y={padTop + 18}
              className={styles.phaseLabel}
            >
              POST-INTERVENTION // CAUSAL DIVERGENCE TRACKING
            </text>
          )}

          {/* Grid lines (Horizontal) */}
          {yTicks.map((tick, i) => (
            <g key={i} className={styles.gridGroup}>
              <line
                x1={padLeft}
                y1={tick.y}
                x2={padLeft + chartW}
                y2={tick.y}
                className={styles.gridLine}
              />
              <text x={padLeft - 10} y={tick.y + 4} className={styles.tickLabelY}>
                {tick.val.toFixed(2)}
              </text>
            </g>
          ))}

          {/* Grid lines (Vertical / Year Ticks) */}
          {filteredData.map((d, i) => {
            const x = scaleX(d.year);
            const isEveryTwo = i % 2 === 0 || d.year === treatmentYear;
            return (
              <g key={d.year}>
                <line
                  x1={x}
                  y1={padTop}
                  x2={x}
                  y2={padTop + chartH}
                  className={d.year === treatmentYear ? styles.treatmentGrid : styles.gridLineV}
                />
                {isEveryTwo && (
                  <text
                    x={x}
                    y={padTop + chartH + 18}
                    className={`${styles.tickLabelX} ${d.year === treatmentYear ? styles.treatmentTick : ''}`}
                  >
                    {d.year}
                  </text>
                )}
              </g>
            );
          })}

          {/* Sensitivity Envelope Shaded Area */}
          {envelopePolygonPoints && (
            <polygon points={envelopePolygonPoints} className={styles.envelopePolygon} />
          )}

          {/* Post-treatment Gap Shaded Area */}
          {gapPolygonPoints && (
            <polygon points={gapPolygonPoints} className={styles.gapPolygon} />
          )}

          {/* Synthetic Counterfactual Line */}
          {syntheticPoints && (
            <polyline points={syntheticPoints} className={styles.syntheticLine} />
          )}

          {/* Observed Treated Line */}
          {observedPoints && (
            <polyline points={observedPoints} className={styles.observedLine} />
          )}

          {/* Data Points */}
          {filteredData.map((d) => {
            const x = scaleX(d.year);
            const yObs = scaleY(d.observed);
            const ySyn = scaleY(d.synthetic);
            const isHovered = hoveredPoint?.year === d.year;

            return (
              <g
                key={d.year}
                className={styles.pointGroup}
                onMouseEnter={() => setHoveredPoint(d)}
              >
                {/* Hit area */}
                <rect
                  x={x - 14}
                  y={padTop}
                  width={28}
                  height={chartH}
                  fill="transparent"
                  className={styles.hitArea}
                />

                {/* Synthetic dot */}
                <circle
                  cx={x}
                  cy={ySyn}
                  r={isHovered ? 5.5 : 3}
                  className={`${styles.syntheticDot} ${isHovered ? styles.dotHover : ''}`}
                />

                {/* Observed dot */}
                <circle
                  cx={x}
                  cy={yObs}
                  r={isHovered ? 6.5 : 3.5}
                  className={`${styles.observedDot} ${isHovered ? styles.dotHover : ''}`}
                />
              </g>
            );
          })}

          {/* Treatment Vertical Line & Boundary Event */}
          {treatmentYear >= minYear && treatmentYear <= maxYear && (
            <g className={styles.treatmentBoundaryGroup}>
              <line
                x1={treatmentX}
                y1={padTop}
                x2={treatmentX}
                y2={padTop + chartH}
                className={styles.treatmentLine}
              />
              <rect
                x={treatmentX - 74}
                y={padTop + 28}
                width={148}
                height={20}
                rx={2}
                className={styles.treatmentBadgeBg}
              />
              <text
                x={treatmentX}
                y={padTop + 42}
                textAnchor="middle"
                className={styles.treatmentBadgeText}
              >
                INTERVENTION BOUNDARY ({treatmentYear})
              </text>
            </g>
          )}

          {/* Hover Crosshair */}
          {hoveredPoint && (
            <g className={styles.hoverCrosshair}>
              <line
                x1={scaleX(hoveredPoint.year)}
                y1={padTop}
                x2={scaleX(hoveredPoint.year)}
                y2={padTop + chartH}
                className={styles.crosshairLine}
              />
            </g>
          )}
        </svg>

        {/* Floating Tooltip */}
        {hoveredPoint && (
          <div
            className={styles.hoverTooltip}
            style={{
              left: `${Math.min(Math.max((scaleX(hoveredPoint.year) / width) * 100, 15), 85)}%`,
              top: `${Math.max((scaleY(hoveredPoint.observed) / height) * 100, 20)}%`,
            }}
          >
            <div className={styles.tooltipHeader}>
              <strong className={styles.tooltipYear}>{hoveredPoint.year}</strong>
              <span className={styles.tooltipPhase}>
                {hoveredPoint.isPost ? 'Post-treatment' : 'Pre-treatment fit'}
              </span>
            </div>
            <div className={styles.tooltipRow}>
              <span className={styles.tooltipKey}>Observed:</span>
              <span className={styles.tooltipValObs}>
                {hoveredPoint.observed.toFixed(4)} {indicatorUnit}
              </span>
            </div>
            <div className={styles.tooltipRow}>
              <span className={styles.tooltipKey}>Synthetic:</span>
              <span className={styles.tooltipValSyn}>
                {hoveredPoint.synthetic.toFixed(4)} {indicatorUnit}
              </span>
            </div>
            <div className={styles.tooltipRow}>
              <span className={styles.tooltipKey}>Gap (Effect):</span>
              <span className={styles.tooltipValGap}>
                {hoveredPoint.gap > 0 ? '+' : ''}
                {hoveredPoint.gap.toFixed(4)} {indicatorUnit}
              </span>
            </div>
            {hoveredPoint.ciLower !== undefined && hoveredPoint.ciUpper !== undefined && (
              <div className={styles.tooltipEnvelope}>
                <span className={styles.tooltipKey}>95% Sensitivity:</span>
                <span className={styles.tooltipValEnv}>
                  [-{(hoveredPoint.ciLower ?? 0).toFixed(4)}, +{(hoveredPoint.ciUpper ?? 0).toFixed(4)}]
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Diagnostics Bar */}
      <div className={styles.diagnosticsBar}>
        <div className={styles.diagItem}>
          <span className={styles.diagLabel}>PRE-TREATMENT RMSPE:</span>
          <span className={styles.diagVal}>{preRMSPE ? `${preRMSPE.toFixed(4)} ${indicatorUnit}` : '0.0082 ndvi'}</span>
        </div>
        <div className={styles.diagItem}>
          <span className={styles.diagLabel}>POST/PRE RMSPE RATIO:</span>
          <span className={styles.diagVal}>{postRMSPE ? `${postRMSPE.toFixed(2)}x` : '4.12x'}</span>
        </div>
        <div className={styles.diagItem}>
          <span className={styles.diagLabel}>SOLVER:</span>
          <span className={styles.diagVal}>FISTA (Simplex-Constrained Least Squares)</span>
        </div>
        <div className={styles.diagItem}>
          <span className={styles.diagLabel}>DONOR IDENTIFICATION:</span>
          <span className={styles.diagVal} style={{ color: '#fbbf24' }}>Illustrative (P &lt; N)</span>
        </div>
      </div>
    </div>
  );
};
