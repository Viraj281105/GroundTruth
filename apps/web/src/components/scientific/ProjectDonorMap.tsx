'use client';

import React, { useState } from 'react';
import { DonorMapUnit } from '../../lib/fixtures/simulated-data';
import { Badge } from '../ui/Badge';
import { MapPin, ShieldAlert, CheckCircle, Navigation, Compass, Layers, Sliders } from 'lucide-react';
import styles from './ProjectDonorMap.module.css';

export interface ProjectDonorMapProps {
  donors: DonorMapUnit[];
  searchRegion?: string;
  worstSMD?: number;
  className?: string;
}

const COVARIATE_BALANCE = [
  { name: 'Rainfall (CHIRPS)', unit: 'mm', treated: 840, donorMean: 832, smd: 0.082, balanced: true },
  { name: 'Elevation (SRTM)', unit: 'm', treated: 720, donorMean: 745, smd: 0.114, balanced: true },
  { name: 'Terrain Slope', unit: 'deg', treated: 4.8, donorMean: 5.1, smd: 0.075, balanced: true },
  { name: 'Road Distance (OSM)', unit: 'km', treated: 18.2, donorMean: 16.9, smd: 0.142, balanced: true },
  { name: 'Population Density', unit: 'per km²', treated: 12.4, donorMean: 14.1, smd: 0.182, balanced: true },
];

export const ProjectDonorMap: React.FC<ProjectDonorMapProps> = ({
  donors,
  searchRegion = 'Southern African Miombo Woodland Outside Protected Areas',
  worstSMD = 0.182,
  className = '',
}) => {
  const [selectedUnit, setSelectedUnit] = useState<DonorMapUnit | null>(
    donors.find((d) => d.status === 'project') || donors[0] || null
  );
  const [activeTab, setActiveTab] = useState<'unit' | 'balance' | 'exclusions'>('unit');

  // SVG coordinates projection
  const lats = donors.map((d) => d.lat);
  const lngs = donors.map((d) => d.lng);
  const minLat = Math.min(...lats) - 0.6;
  const maxLat = Math.max(...lats) + 0.6;
  const minLng = Math.min(...lngs) - 0.6;
  const maxLng = Math.max(...lngs) + 0.6;

  const width = 640;
  const height = 380;
  const pad = 44;

  const projX = (lng: number) =>
    pad + ((lng - minLng) / Math.max(maxLng - minLng, 0.001)) * (width - pad * 2);
  const projY = (lat: number) =>
    pad + ((maxLat - lat) / Math.max(maxLat - minLat, 0.001)) * (height - pad * 2);

  const projectUnit = donors.find((d) => d.status === 'project');
  const excludedUnits = donors.filter((d) => d.status === 'excluded');
  const admittedUnits = donors.filter((d) => d.status === 'admitted');

  return (
    <div className={`${styles.container} ${className}`}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleCol}>
          <div className={styles.titleRow}>
            <Compass size={18} className={styles.compassIcon} />
            <h4 className={styles.title}>Donor Pool & Spatial Balance Map</h4>
            <Badge tone="info" size="sm" variant="subtle">
              WORST SMD: {worstSMD.toFixed(3)}
            </Badge>
            <Badge tone="positive" size="sm" variant="subtle">
              BALANCED (≤ 0.25)
            </Badge>
          </div>
          <p className={styles.subtitle}>
            Search Region: <em>{searchRegion}</em>
          </p>
        </div>

        {/* Legend */}
        <div className={styles.legend}>
          <div className={styles.legendItem}>
            <span className={styles.dotProject} />
            <span>Project Area</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.dotAdmitted} />
            <span>Admitted ({admittedUnits.length})</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.dotExcluded} />
            <span>Excluded ({excludedUnits.length})</span>
          </div>
        </div>
      </div>

      {/* Main Area: Map Viewport + Tabbed Detail Panel */}
      <div className={styles.mainArea}>
        {/* SVG GIS Radar Viewport */}
        <div className={styles.mapWrapper}>
          <svg viewBox={`0 0 ${width} ${height}`} className={styles.mapSvg}>
            {/* Background Grid & Boundaries Simulation */}
            <rect width={width} height={height} className={styles.mapBg} />

            {/* Radar Concentric Distance Caliper Rings centered on Project */}
            {projectUnit && (
              <g className={styles.caliperRings}>
                {/* 10 km Leakage Belt */}
                <circle
                  cx={projX(projectUnit.lng)}
                  cy={projY(projectUnit.lat)}
                  r={32}
                  className={styles.leakageBelt}
                />
                <text
                  x={projX(projectUnit.lng) + 36}
                  y={projY(projectUnit.lat) - 6}
                  className={styles.caliperLabel}
                >
                  10 km leakage belt
                </text>

                {/* 100 km Caliper Ring */}
                <circle
                  cx={projX(projectUnit.lng)}
                  cy={projY(projectUnit.lat)}
                  r={75}
                  className={styles.caliperRing}
                />
                <text
                  x={projX(projectUnit.lng) + 80}
                  y={projY(projectUnit.lat) - 4}
                  className={styles.caliperLabel}
                >
                  100 km
                </text>

                {/* 250 km Caliper Ring */}
                <circle
                  cx={projX(projectUnit.lng)}
                  cy={projY(projectUnit.lat)}
                  r={140}
                  className={styles.caliperRing}
                />
                <text
                  x={projX(projectUnit.lng) + 145}
                  y={projY(projectUnit.lat) - 4}
                  className={styles.caliperLabel}
                >
                  250 km
                </text>
              </g>
            )}

            {/* Coordinate Grid Guide lines */}
            {[0.25, 0.5, 0.75].map((pct) => (
              <line
                key={`h-${pct}`}
                x1={0}
                y1={height * pct}
                x2={width}
                y2={height * pct}
                className={styles.coordLine}
              />
            ))}
            {[0.25, 0.5, 0.75].map((pct) => (
              <line
                key={`v-${pct}`}
                x1={width * pct}
                y1={0}
                x2={width * pct}
                y2={height}
                className={styles.coordLine}
              />
            ))}

            {/* Connection Lines from Project to Admitted Donors */}
            {projectUnit &&
              admittedUnits.map((d) => (
                <line
                  key={`conn-${d.id}`}
                  x1={projX(projectUnit.lng)}
                  y1={projY(projectUnit.lat)}
                  x2={projX(d.lng)}
                  y2={projY(d.lat)}
                  className={styles.connectionLine}
                  strokeWidth={Math.max((d.weight ?? 0.1) * 6, 1.2)}
                />
              ))}

            {/* Donor Points */}
            {donors.map((unit) => {
              const x = projX(unit.lng);
              const y = projY(unit.lat);
              const isSelected = selectedUnit?.id === unit.id;
              const isProject = unit.status === 'project';
              const isAdmitted = unit.status === 'admitted';

              return (
                <g
                  key={unit.id}
                  tabIndex={0}
                  role="button"
                  aria-label={`${unit.name} (${unit.status})`}
                  className={styles.unitMarker}
                  onClick={() => setSelectedUnit(unit)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedUnit(unit);
                    }
                  }}
                >
                  {/* Outer selection ring */}
                  {isSelected && (
                    <circle
                      cx={x}
                      cy={y}
                      r={isProject ? 17 : 13}
                      className={styles.selectionRing}
                    />
                  )}

                  {/* Marker Dot */}
                  <circle
                    cx={x}
                    cy={y}
                    r={isProject ? 9 : isAdmitted ? 6 : 4.5}
                    className={`${styles.markerDot} ${styles[unit.status]}`}
                  />

                  {/* Weight label for top admitted donors */}
                  {isAdmitted && unit.weight && unit.weight > 0.15 && (
                    <text
                      x={x + 9}
                      y={y + 4}
                      className={styles.weightLabel}
                    >
                      {(unit.weight * 100).toFixed(0)}%
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Tabbed Inspector Panel */}
        <div className={styles.inspectorPanel}>
          <div className={styles.inspectorNav}>
            <button
              className={`${styles.inspectorTab} ${activeTab === 'unit' ? styles.inspectorTabActive : ''}`}
              onClick={() => setActiveTab('unit')}
            >
              Unit Detail
            </button>
            <button
              className={`${styles.inspectorTab} ${activeTab === 'balance' ? styles.inspectorTabActive : ''}`}
              onClick={() => setActiveTab('balance')}
            >
              Balance SMD
            </button>
            <button
              className={`${styles.inspectorTab} ${activeTab === 'exclusions' ? styles.inspectorTabActive : ''}`}
              onClick={() => setActiveTab('exclusions')}
            >
              Exclusions ({excludedUnits.length})
            </button>
          </div>

          <div className={styles.inspectorBody}>
            {/* Tab 1: Unit Detail */}
            {activeTab === 'unit' && selectedUnit && (
              <div className={styles.unitCard}>
                <div className={styles.unitCardHeader}>
                  <div className={styles.unitStatusIcon}>
                    {selectedUnit.status === 'project' ? (
                      <MapPin className={styles.projectIcon} size={18} />
                    ) : selectedUnit.status === 'admitted' ? (
                      <CheckCircle className={styles.admittedIcon} size={18} />
                    ) : (
                      <ShieldAlert className={styles.excludedIcon} size={18} />
                    )}
                  </div>
                  <div className={styles.unitTitleCol}>
                    <span className={styles.unitStatusTag}>
                      {selectedUnit.status.toUpperCase()}
                    </span>
                    <h5 className={styles.unitName}>{selectedUnit.name}</h5>
                  </div>
                </div>

                <div className={styles.unitMetaList}>
                  <div className={styles.unitMetaRow}>
                    <span className={styles.metaKey}>Unit ID:</span>
                    <span className={styles.metaValMono}>{selectedUnit.id}</span>
                  </div>
                  <div className={styles.unitMetaRow}>
                    <span className={styles.metaKey}>Distance to Project:</span>
                    <span className={styles.metaVal}>{selectedUnit.distanceKm} km</span>
                  </div>
                  <div className={styles.unitMetaRow}>
                    <span className={styles.metaKey}>Coordinates:</span>
                    <span className={styles.metaValMono}>
                      {selectedUnit.lat.toFixed(2)}°, {selectedUnit.lng.toFixed(2)}°
                    </span>
                  </div>

                  {selectedUnit.weight !== undefined && (
                    <div className={styles.unitMetaRow}>
                      <span className={styles.metaKey}>Synthetic Weight:</span>
                      <span className={styles.metaValWeight}>
                        {(selectedUnit.weight * 100).toFixed(1)}% ({selectedUnit.weight.toFixed(4)})
                      </span>
                    </div>
                  )}

                  {selectedUnit.smd !== undefined && (
                    <div className={styles.unitMetaRow}>
                      <span className={styles.metaKey}>Post-Match SMD:</span>
                      <span className={styles.metaVal}>{selectedUnit.smd.toFixed(3)}</span>
                    </div>
                  )}

                  {selectedUnit.exclusionReason && (
                    <div className={styles.exclusionBox}>
                      <span className={styles.exclusionLabel}>EXCLUSION RULE:</span>
                      <p className={styles.exclusionReason}>
                        {selectedUnit.exclusionReason}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tab 2: Balance SMD Table */}
            {activeTab === 'balance' && (
              <div className={styles.balanceTab}>
                <div className={styles.balanceHeader}>
                  <span className={styles.balanceDesc}>
                    Standardised Mean Differences across covariates. Target: SMD ≤ 0.25.
                  </span>
                </div>
                <div className={styles.balanceTable}>
                  {COVARIATE_BALANCE.map((cov, idx) => (
                    <div key={idx} className={styles.balanceRow}>
                      <div className={styles.balanceCovCol}>
                        <span className={styles.covName}>{cov.name}</span>
                        <span className={styles.covUnit}>
                          {cov.treated} vs {cov.donorMean} {cov.unit}
                        </span>
                      </div>
                      <div className={styles.balanceSmdCol}>
                        <div className={styles.balanceTrack} title={`SMD ${cov.smd.toFixed(3)} (Threshold: 0.250)`}>
                          <div
                            className={styles.balanceFill}
                            style={{ width: `${Math.min((cov.smd / 0.25) * 100, 100)}%` }}
                          />
                        </div>
                        <span className={styles.smdVal}>{cov.smd.toFixed(3)} SMD</span>
                        <Badge tone="positive" size="sm" variant="subtle">
                          PASS
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tab 3: Exclusions Log */}
            {activeTab === 'exclusions' && (
              <div className={styles.exclusionsTab}>
                <p className={styles.exclusionsIntro}>
                  Every excluded candidate region carries a documented rule violation to prevent cherry-picking.
                </p>
                <div className={styles.exclusionsList}>
                  {excludedUnits.map((ex) => (
                    <div
                      key={ex.id}
                      className={styles.exclusionItem}
                      onClick={() => {
                        setSelectedUnit(ex);
                        setActiveTab('unit');
                      }}
                    >
                      <div className={styles.exItemHeader}>
                        <strong className={styles.exName}>{ex.name}</strong>
                        <span className={styles.exDist}>{ex.distanceKm} km</span>
                      </div>
                      <span className={styles.exReason}>{ex.exclusionReason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
