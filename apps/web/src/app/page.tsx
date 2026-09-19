'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { getCases } from '../lib/api';
import { CaseSummary } from '../lib/types';
import { formatHectares } from '../lib/formatters';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { StatusIndicator } from '../components/ui/StatusIndicator';
import {
  Search,
  ArrowRight,
  Shield,
  Layers,
  Activity,
  AlertTriangle,
  Globe2,
  Calendar,
  CheckCircle,
  FileText,
  SlidersHorizontal,
  Compass,
} from 'lucide-react';
import styles from './page.module.css';

export default function CaseBrowserPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [standardFilter, setStandardFilter] = useState('all');
  const [sortBy, setSortBy] = useState<'name' | 'pre_period'>('name');
  const [isLoading, setIsLoading] = useState(true);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    async function loadCases() {
      setIsLoading(true);
      const data = await getCases();
      setCases(data);
      setIsLoading(false);
    }
    loadCases();
  }, []);

  // Keyboard shortcut '/' to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== searchInputRef.current) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const standards = ['all', ...new Set(cases.map((c) => c.standard))];

  const filteredCases = cases
    .filter((c) => {
      const matchesStandard = standardFilter === 'all' || c.standard === standardFilter;
      const matchesSearch =
        searchQuery === '' ||
        c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.case_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.country.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.ecosystem.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesStandard && matchesSearch;
    })
    .sort((a, b) => {
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      if (sortBy === 'pre_period') return a.pre_period.localeCompare(b.pre_period);
      return 0;
    });

  return (
    <div id="main-content" className="gt-container gt-radar-bg" style={{ paddingTop: '32px', paddingBottom: '60px' }}>
      {/* Hero Section */}
      <div className={styles.hero}>
        <div className={styles.heroBadgeRow}>
          <Badge tone="info" size="md" variant="subtle" icon={<Compass size={13} />}>
            SYNTHETIC CONTROL ENGINE // SATELLITE EO-INFERENCE V0.2
          </Badge>
          <Badge tone="neutral" size="md" variant="outline">
            AST CONTRACT BOUNDARY ENFORCED
          </Badge>
          <Badge tone="simulated" size="md" variant="subtle">
            DETERMINISTIC SIMULATION MODE
          </Badge>
        </div>

        <h1 className={styles.heroTitle}>
          VERIFY WHAT CHANGED. NOT JUST WHAT WAS CLAIMED.
        </h1>
        <p className={styles.heroSubtitle}>
          Independent satellite-driven causal inference for ecosystem restoration & carbon claims.
          Disentangling true intervention impact from counterfactual drift.
        </p>

        {/* Live Telemetry Ticker Ribbon */}
        <div className={styles.telemetryTicker}>
          <div className={styles.tickerItem}>
            <span className={styles.tickerDot} />
            <span className={styles.tickerLabel}>SATELLITE INGESTION:</span>
            <span className={styles.tickerVal}>SENTINEL-2 / LANDSAT NBAR</span>
          </div>
          <div className={styles.tickerItem}>
            <span className={styles.tickerLabel}>DONOR POOL CALIPER:</span>
            <span className={styles.tickerVal}>MAHALANOBIS COVARIATE BALANCED</span>
          </div>
          <div className={styles.tickerItem}>
            <span className={styles.tickerLabel}>CRYPTOGRAPHIC PROOF:</span>
            <span className={styles.tickerVal}>SHA-256 ATTESTATION</span>
          </div>
          <div className={styles.tickerItem}>
            <span className={styles.tickerLabel}>DATA MODE:</span>
            <span className={styles.tickerVal} style={{ color: '#fbbf24' }}>SIMULATED FIXTURES</span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <span className={styles.statValue}>3</span>
            <span className={styles.statLabel}>ACTIVE INVESTIGATIONS</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue} style={{ color: 'var(--gt-verdict-consistent-text)' }}>
              0
            </span>
            <span className={styles.statLabel}>ANALYSED ON REAL DATA</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue} style={{ color: 'var(--gt-accent-cyan)' }}>
              100%
            </span>
            <span className={styles.statLabel}>MANDATORY PROVENANCE</span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statValue} style={{ color: '#fbbf24' }}>
              INCONCLUSIVE
            </span>
            <span className={styles.statLabel}>NEUTRAL SCIENTIFIC STATE</span>
          </div>
        </div>
      </div>

      {/* Honest Status Banner */}
      <div className={styles.honestNotice}>
        <div className={styles.noticeIconCol}>
          <AlertTriangle size={20} className={styles.noticeIcon} />
        </div>
        <div className={styles.noticeTextCol}>
          <strong className={styles.noticeTitle}>Honest Verification Status:</strong>
          <p className={styles.noticeDesc}>
            No real-world project has been verified on live Earth-observation data yet. All currently available analyses run on deterministic simulated fixtures. Mikoko Pamoja demonstrates that the pipeline correctly returns <code style={{ color: '#cbd5e1' }}>INCONCLUSIVE</code> when project scale is below satellite resolution.
          </p>
        </div>
      </div>

      {/* Filter & Search Controls */}
      <div className={styles.controlsBar}>
        <div className={styles.searchWrapper}>
          <Search size={16} className={styles.searchIcon} />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search projects, countries, ecosystems... (Press '/' to focus)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={styles.searchInput}
            aria-label="Search cases"
          />
          <span className={styles.hotkeyTag}>/</span>
          {searchQuery && (
            <button
              type="button"
              className={styles.clearBtn}
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
            >
              Clear
            </button>
          )}
        </div>

        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>STANDARD:</span>
          {standards.map((std) => (
            <button
              key={std}
              type="button"
              className={`${styles.filterBtn} ${standardFilter === std ? styles.filterBtnActive : ''}`}
              onClick={() => setStandardFilter(std)}
            >
              {std.toUpperCase()}
            </button>
          ))}
        </div>

        <div className={styles.sortGroup}>
          <SlidersHorizontal size={13} className={styles.sortIcon} />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className={styles.sortSelect}
            aria-label="Sort projects"
          >
            <option value="name">Sort by Name</option>
            <option value="pre_period">Sort by Baseline Year</option>
          </select>
        </div>
      </div>

      {/* Case Cards Grid */}
      <div className={styles.casesGrid}>
        {filteredCases.map((c) => {
          const coords =
            c.case_id === 'kariba-redd'
              ? '17°12\'S, 28°45\'E'
              : c.case_id === 'mikoko-pamoja'
              ? '4°25\'S, 39°31\'E'
              : '11°30\'N, 103°30\'E';

          return (
            <Card key={c.case_id} variant="interactive" className={styles.caseCard}>
              <CardHeader>
                <div className={styles.cardHeaderTop}>
                  <div className={styles.cardBadges}>
                    <Badge tone="info" size="sm" variant="subtle">
                      {c.standard}
                    </Badge>
                    <span className={styles.coordText}>[{coords}]</span>
                  </div>
                  <StatusIndicator status={c.status as any} />
                </div>
                <CardTitle>{c.name}</CardTitle>
                <CardDescription>
                  <Globe2 size={13} style={{ display: 'inline', marginRight: '4px' }} />
                  {c.country} · {c.ecosystem}
                </CardDescription>
              </CardHeader>

              <CardContent>
                <div className={styles.metaTable}>
                  <div className={styles.metaRow}>
                    <span className={styles.metaKey}>Registry ID:</span>
                    <span className={styles.metaValMono}>{c.registry_id || 'Pending'}</span>
                  </div>
                  <div className={styles.metaRow}>
                    <span className={styles.metaKey}>Target Indicator:</span>
                    <span className={styles.metaValMono}>{c.indicator.toUpperCase()}</span>
                  </div>
                  <div className={styles.metaRow}>
                    <span className={styles.metaKey}>Baseline Pre-Period:</span>
                    <span className={styles.metaValMono}>{c.pre_period}</span>
                  </div>
                  <div className={styles.metaRow}>
                    <span className={styles.metaKey}>Crediting Post-Period:</span>
                    <span className={styles.metaValMono}>{c.post_period}</span>
                  </div>
                  {c.has_known_reference && (
                    <div className={styles.knownRefTag}>
                      <CheckCircle size={12} style={{ color: 'var(--gt-accent-cyan)' }} />
                      <span>Published 3rd-Party Reference Target</span>
                    </div>
                  )}
                </div>
              </CardContent>

              <CardFooter>
                <Link href={`/cases/${c.case_id}`} style={{ width: '100%' }}>
                  <Button variant="primary" size="md" style={{ width: '100%' }} rightIcon={<ArrowRight size={15} />}>
                    Open Investigation Dossier
                  </Button>
                </Link>
              </CardFooter>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
