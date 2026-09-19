'use client';

import React, { useState } from 'react';
import { Evidence } from '../../lib/types';
import { formatEvidenceValue, formatConfidenceInterval } from '../../lib/formatters';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { ProvenanceDrawer } from '../ui/ProvenanceDrawer';
import { Database, Search, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown, GitBranch, Table, CheckCircle2, Shield, Satellite, Layers, Activity, Lock } from 'lucide-react';
import styles from './EvidenceExplorer.module.css';

export interface EvidenceExplorerProps {
  items: Evidence[];
  className?: string;
}

type SortField = 'id' | 'label' | 'value' | 'stage';
type SortOrder = 'asc' | 'desc';
type ViewMode = 'dag' | 'table';

export const EvidenceExplorer: React.FC<EvidenceExplorerProps> = ({
  items,
  className = '',
}) => {
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('dag');
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('stage');
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');

  const stages = ['all', ...new Set(items.map((it) => it.provenance.stage))];

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  const filteredItems = items
    .filter((it) => {
      const matchesStage = stageFilter === 'all' || it.provenance.stage === stageFilter;
      const matchesSearch =
        searchQuery === '' ||
        it.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        it.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        it.provenance.method.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesStage && matchesSearch;
    })
    .sort((a, b) => {
      let comparison = 0;
      if (sortField === 'id') comparison = a.id.localeCompare(b.id);
      else if (sortField === 'label') comparison = a.label.localeCompare(b.label);
      else if (sortField === 'stage') comparison = a.provenance.stage.localeCompare(b.provenance.stage);
      else if (sortField === 'value') {
        const valA = typeof a.value === 'number' ? a.value : 0;
        const valB = typeof b.value === 'number' ? b.value : 0;
        comparison = valA - valB;
      }
      return sortOrder === 'asc' ? comparison : -comparison;
    });

  const getStageCount = (stg: string) => {
    if (stg === 'all') return items.length;
    return items.filter((it) => it.provenance.stage === stg).length;
  };

  const renderSortIcon = (field: SortField) => {
    if (sortField !== field) return <ArrowUpDown size={12} className={styles.sortIconDim} />;
    return sortOrder === 'asc' ? (
      <ArrowUp size={12} className={styles.sortIconActive} />
    ) : (
      <ArrowDown size={12} className={styles.sortIconActive} />
    );
  };

  // Group items for DAG stages
  const dagStages = [
    {
      id: 'ingestion',
      name: '1. INGESTION',
      description: 'Registry baseline & raw satellite assets',
      items: items.filter((i) => i.provenance.stage === 'ingestion'),
    },
    {
      id: 'matching',
      name: '2. SPATIAL MATCHING',
      description: 'Caliper distance & donor exclusions',
      items: items.filter((i) => i.provenance.stage === 'matching'),
    },
    {
      id: 'causal',
      name: '3. SYNTHETIC CONTROL',
      description: 'Convex least squares & effect estimates',
      items: items.filter((i) => i.provenance.stage === 'causal'),
    },
    {
      id: 'uncertainty',
      name: '4. ROBUSTNESS & PLACEBOS',
      description: 'In-space permutation & leave-one-out',
      items: items.filter((i) => i.provenance.stage === 'uncertainty'),
    },
  ];

  return (
    <div className={`${styles.container} ${className}`}>
      {/* Top Header & View Toggle Bar */}
      <div className={styles.headerBar}>
        <div className={styles.headerTitleGroup}>
          <div className={styles.headerEyebrow}>EVIDENCE COMMAND CENTER</div>
          <h4 className={styles.headerTitle}>Causal Evidence Graph & Ledger</h4>
        </div>

        <div className={styles.viewToggleGroup}>
          <button
            type="button"
            className={`${styles.viewToggleBtn} ${viewMode === 'dag' ? styles.viewToggleActive : ''}`}
            onClick={() => setViewMode('dag')}
          >
            <GitBranch size={13} />
            <span>CAUSAL EVIDENCE DAG</span>
          </button>
          <button
            type="button"
            className={`${styles.viewToggleBtn} ${viewMode === 'table' ? styles.viewToggleActive : ''}`}
            onClick={() => setViewMode('table')}
          >
            <Table size={13} />
            <span>MATRIX TABLE ({filteredItems.length})</span>
          </button>
        </div>
      </div>

      {/* Filter Toolbar (For Table View) */}
      {viewMode === 'table' && (
        <div className={styles.filterBar}>
          <div className={styles.searchBox}>
            <Search size={15} className={styles.searchIcon} />
            <input
              type="text"
              placeholder="Search evidence items, units, or methods..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.searchInput}
              aria-label="Filter evidence by label, ID, or method"
            />
          </div>

          <div className={styles.stageChips}>
            {stages.map((stg) => (
              <button
                key={stg}
                type="button"
                className={`${styles.stageChip} ${stageFilter === stg ? styles.stageChipActive : ''}`}
                onClick={() => setStageFilter(stg)}
              >
                <span>{stg.toUpperCase()}</span>
                <span className={styles.stageCount}>({getStageCount(stg)})</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* VIEW A: CAUSAL EVIDENCE DAG */}
      {viewMode === 'dag' && (
        <div className={styles.dagContainer}>
          <div className={styles.dagIntro}>
            <div className={styles.dagIntroLeft}>
              <span className={styles.dagIntroBadge}>CRYPTOGRAPHIC CAUSAL LINEAGE</span>
              <p className={styles.dagIntroText}>
                Every finding is deterministically traced back through mathematical transformations to its satellite and registry inputs. Click any node to inspect parameters, upstream inputs, and cryptographic SHA-256 hashes.
              </p>
            </div>
            <div className={styles.dagLiveIndicator}>
              <span className={styles.dagLiveDot} />
              <span>BIT-PERFECT REPRODUCIBLE</span>
            </div>
          </div>

          <div className={styles.dagGrid}>
            {dagStages.map((stg, sIdx) => {
              const isLast = sIdx === dagStages.length - 1;

              return (
                <div key={stg.id} className={styles.dagStageCol}>
                  <div className={styles.dagStageHeader}>
                    <span className={styles.dagStageName}>{stg.name}</span>
                    <span className={styles.dagStageDesc}>{stg.description}</span>
                  </div>

                  <div className={styles.dagNodesList}>
                    {stg.items.map((item) => {
                      const isSelected = selectedEvidence?.id === item.id;
                      const hasInterval = Boolean(item.confidence);

                      return (
                        <div
                          key={item.id}
                          tabIndex={0}
                          role="button"
                          className={`${styles.dagNodeCard} ${isSelected ? styles.dagNodeSelected : ''}`}
                          onClick={() => setSelectedEvidence(item)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              setSelectedEvidence(item);
                            }
                          }}
                        >
                          <div className={styles.dagNodeTop}>
                            <Badge tone="info" size="sm" variant="subtle">
                              {item.provenance.stage.toUpperCase()}
                            </Badge>
                            <span className={styles.dagNodeHash}>
                              #{item.id.slice(0, 8)}
                            </span>
                          </div>

                          <h5 className={styles.dagNodeTitle}>{item.label}</h5>

                          <div className={styles.dagNodeValueRow}>
                            <span className={styles.dagNodeValue}>
                              {formatEvidenceValue(item.value, item.unit)}
                            </span>
                            {hasInterval && item.confidence && (
                              <Badge tone="neutral" size="sm">
                                {formatConfidenceInterval(item.confidence, item.unit)}
                              </Badge>
                            )}
                          </div>

                          <div className={styles.dagNodeFooter}>
                            <span className={styles.dagNodeMethod}>
                              {item.provenance.method}
                            </span>
                            <span className={styles.dagNodeAction}>
                              Audit <ChevronRight size={11} />
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* VIEW B: MATRIX TABLE (Desktop & Mobile) */}
      {viewMode === 'table' && (
        <>
          <div className={styles.tableWrapper}>
            <table className={styles.table} role="table" aria-label="Evidence Bundle Items">
              <thead>
                <tr>
                  <th className={styles.thStage} onClick={() => handleSort('stage')}>
                    <div className={styles.thHeaderContent}>
                      <span>Stage</span>
                      {renderSortIcon('stage')}
                    </div>
                  </th>
                  <th className={styles.thItem} onClick={() => handleSort('label')}>
                    <div className={styles.thHeaderContent}>
                      <span>Evidence Item</span>
                      {renderSortIcon('label')}
                    </div>
                  </th>
                  <th className={styles.thValue} onClick={() => handleSort('value')}>
                    <div className={styles.thHeaderContent}>
                      <span>Value & Unit</span>
                      {renderSortIcon('value')}
                    </div>
                  </th>
                  <th className={styles.thConfidence}>Interval (Kind)</th>
                  <th className={styles.thMethod}>Method & Source</th>
                  <th className={styles.thAction}>Audit</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={6} className={styles.emptyRow}>
                      No evidence items match the current filter.
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((item) => (
                    <tr key={item.id} className={styles.row}>
                      <td className={styles.tdStage}>
                        <Badge tone="neutral" size="sm" variant="subtle">
                          {item.provenance.stage}
                        </Badge>
                      </td>
                      <td className={styles.tdItem}>
                        <div className={styles.itemTitle}>{item.label}</div>
                        <div className={styles.itemId}>{item.id}</div>
                      </td>
                      <td className={styles.tdValue}>
                        <span className={styles.valueNumber}>
                          {formatEvidenceValue(item.value, item.unit)}
                        </span>
                      </td>
                      <td className={styles.tdConfidence}>
                        {item.confidence ? (
                          <Badge tone="info" size="sm" variant="subtle">
                            {formatConfidenceInterval(item.confidence, item.unit)}
                          </Badge>
                        ) : (
                          <span className={styles.noInterval}>—</span>
                        )}
                      </td>
                      <td className={styles.tdMethod}>
                        <div className={styles.methodName}>{item.provenance.method}</div>
                        <div className={styles.sourceName}>{item.provenance.source}</div>
                      </td>
                      <td className={styles.tdAction}>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelectedEvidence(item)}
                          rightIcon={<ChevronRight size={13} />}
                          aria-label={`View provenance for ${item.label}`}
                        >
                          Audit
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile Cards View (< 768px) */}
          <div className={styles.mobileCardsList}>
            {filteredItems.map((item) => (
              <div key={item.id} className={styles.mobileCard}>
                <div className={styles.mobileCardHeader}>
                  <Badge tone="info" size="sm" variant="subtle">
                    {item.provenance.stage.toUpperCase()}
                  </Badge>
                  <span className={styles.mobileCardId}>{item.id}</span>
                </div>
                <h5 className={styles.mobileCardTitle}>{item.label}</h5>
                <div className={styles.mobileCardValueRow}>
                  <span className={styles.mobileCardValue}>
                    {formatEvidenceValue(item.value, item.unit)}
                  </span>
                  {item.confidence && (
                    <Badge tone="neutral" size="sm">
                      {formatConfidenceInterval(item.confidence, item.unit)}
                    </Badge>
                  )}
                </div>
                <div className={styles.mobileCardFooter}>
                  <span className={styles.mobileCardMethod}>{item.provenance.method}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setSelectedEvidence(item)}
                    rightIcon={<ChevronRight size={13} />}
                  >
                    Audit
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Provenance Drawer (2-Click Provenance Rule) */}
      <ProvenanceDrawer
        evidence={selectedEvidence}
        isOpen={Boolean(selectedEvidence)}
        onClose={() => setSelectedEvidence(null)}
      />
    </div>
  );
};

