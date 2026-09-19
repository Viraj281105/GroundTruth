'use client';

import React, { useState } from 'react';
import { Badge } from '../ui/Badge';
import { Calendar, Satellite, Flame, Shield, CheckCircle, Info, Filter } from 'lucide-react';
import styles from './ProjectTimeline.module.css';

export interface TimelineEvent {
  year: number;
  title: string;
  description: string;
  type: 'baseline' | 'crediting' | 'sensor' | 'disturbance';
}

export interface ProjectTimelineProps {
  events: TimelineEvent[];
  creditingStartYear?: number;
  className?: string;
}

const TYPE_CONFIG = {
  baseline: {
    icon: <Calendar size={15} />,
    badgeTone: 'neutral' as const,
    label: 'BASELINE FIT',
  },
  crediting: {
    icon: <Shield size={15} />,
    badgeTone: 'positive' as const,
    label: 'CREDITING START',
  },
  sensor: {
    icon: <Satellite size={15} />,
    badgeTone: 'info' as const,
    label: 'SENSOR TRANSITION',
  },
  disturbance: {
    icon: <Flame size={15} />,
    badgeTone: 'caution' as const,
    label: 'DISTURBANCE ANOMALY',
  },
};

export const ProjectTimeline: React.FC<ProjectTimelineProps> = ({
  events,
  creditingStartYear = 2011,
  className = '',
}) => {
  const [filterType, setFilterType] = useState<string>('all');

  const filteredEvents = events.filter((evt) => {
    if (filterType === 'all') return true;
    return evt.type === filterType;
  });

  return (
    <div className={`${styles.container} ${className}`}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleArea}>
          <div className={styles.titleRow}>
            <h4 className={styles.title}>Project & Sensor History Timeline</h4>
            <Badge tone="info" size="sm" variant="subtle">
              CROSS-CALIBRATED SERIES
            </Badge>
          </div>
          <p className={styles.subtitle}>
            Chronology of satellite sensor transitions, project crediting milestones, and environmental disturbances.
          </p>
        </div>

        {/* Filter Pills */}
        <div className={styles.filterBar}>
          <Filter size={13} className={styles.filterIcon} />
          <button
            className={`${styles.filterPill} ${filterType === 'all' ? styles.filterPillActive : ''}`}
            onClick={() => setFilterType('all')}
          >
            All Events ({events.length})
          </button>
          <button
            className={`${styles.filterPill} ${filterType === 'sensor' ? styles.filterPillActive : ''}`}
            onClick={() => setFilterType('sensor')}
          >
            Sensor Transitions ({events.filter((e) => e.type === 'sensor').length})
          </button>
          <button
            className={`${styles.filterPill} ${filterType === 'crediting' ? styles.filterPillActive : ''}`}
            onClick={() => setFilterType('crediting')}
          >
            Crediting ({events.filter((e) => e.type === 'crediting').length})
          </button>
          <button
            className={`${styles.filterPill} ${filterType === 'disturbance' ? styles.filterPillActive : ''}`}
            onClick={() => setFilterType('disturbance')}
          >
            Disturbances ({events.filter((e) => e.type === 'disturbance').length})
          </button>
        </div>
      </div>

      {/* Sensor Transition Methodology Note */}
      <div className={styles.methodologyNote}>
        <Info size={16} className={styles.noteIcon} />
        <p className={styles.noteText}>
          <strong>Sensor Transition Guard:</strong> Changes in satellite instruments (e.g., Landsat 7 SLC-off in 2003, Landsat 8 in 2013, Sentinel-2 in 2015) can introduce artificial step-changes in spectral indices. GroundTruth places sensor transitions within the pre-treatment fitting window and includes cross-sensor sensitivity checks in the specification curve.
        </p>
      </div>

      {/* Timeline Nodes */}
      <div className={styles.timelineList}>
        {filteredEvents.map((evt, idx) => {
          const config = TYPE_CONFIG[evt.type] || TYPE_CONFIG.baseline;
          const isTreatment = evt.year === creditingStartYear;

          return (
            <div
              key={idx}
              className={`${styles.timelineItem} ${isTreatment ? styles.treatmentItem : ''}`}
            >
              {/* Year column */}
              <div className={styles.yearCol}>
                <span className={styles.yearText}>{evt.year}</span>
              </div>

              {/* Spine Node */}
              <div className={styles.spineCol}>
                <div className={`${styles.node} ${styles[evt.type]}`}>
                  {config.icon}
                </div>
                {idx < filteredEvents.length - 1 && <div className={styles.spineLine} />}
              </div>

              {/* Content Card */}
              <div className={styles.contentCol}>
                <div className={styles.cardHeader}>
                  <Badge tone={config.badgeTone} size="sm" variant="subtle">
                    {config.label}
                  </Badge>
                  <h5 className={styles.cardTitle}>{evt.title}</h5>
                </div>
                <p className={styles.cardDesc}>{evt.description}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
