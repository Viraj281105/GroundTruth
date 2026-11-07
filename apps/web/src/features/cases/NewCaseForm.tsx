'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button, LinkButton } from '../../components/ds';
import { getApiBaseUrl } from '../../lib/api';
import styles from './NewCaseForm.module.css';

interface Preset {
  label: string;
  name: string;
  standard: string;
  registry_id: string;
  country: string;
  ecosystem: string;
  area_ha: number;
  crediting_period_start: string;
  crediting_period_end: string;
  claimed_credits_tco2e: number;
  indicator: string;
  pre_start: number;
  pre_end: number;
  post_start: number;
  post_end: number;
}

const PRESETS: Preset[] = [
  {
    label: 'Tambopata-Bahuaja (VCS 1067)',
    name: 'Tambopata-Bahuaja Biodiversity Reserve',
    standard: 'VCS',
    registry_id: 'VCS 1067',
    country: 'Peru',
    ecosystem: 'Amazonian tropical moist forest',
    area_ha: 246829,
    crediting_period_start: '2010-01-01',
    crediting_period_end: '2039-12-31',
    claimed_credits_tco2e: 4500000,
    indicator: 'ndvi',
    pre_start: 2002,
    pre_end: 2009,
    post_start: 2010,
    post_end: 2022,
  },
  {
    label: 'Cordillera Azul (VCS 985)',
    name: 'Cordillera Azul National Park REDD+ Project',
    standard: 'VCS',
    registry_id: 'VCS 985',
    country: 'Peru',
    ecosystem: 'Montane & premontane cloud forest',
    area_ha: 1350000,
    crediting_period_start: '2008-08-07',
    crediting_period_end: '2038-08-06',
    claimed_credits_tco2e: 20000000,
    indicator: 'ndvi',
    pre_start: 2000,
    pre_end: 2007,
    post_start: 2008,
    post_end: 2022,
  },
  {
    label: 'Keo Seima (VCS 1650)',
    name: 'Keo Seima Wildlife Sanctuary REDD+ Project',
    standard: 'VCS',
    registry_id: 'VCS 1650',
    country: 'Cambodia',
    ecosystem: 'Deciduous & semi-evergreen forest',
    area_ha: 292690,
    crediting_period_start: '2010-01-01',
    crediting_period_end: '2040-12-31',
    claimed_credits_tco2e: 17400000,
    indicator: 'evi',
    pre_start: 2002,
    pre_end: 2009,
    post_start: 2010,
    post_end: 2022,
  },
];

export function NewCaseForm() {
  const router = useRouter();

  const [name, setName] = useState('Tambopata-Bahuaja Biodiversity Reserve');
  const [standard, setStandard] = useState('VCS');
  const [registryId, setRegistryId] = useState('VCS 1067');
  const [country, setCountry] = useState('Peru');
  const [ecosystem, setEcosystem] = useState('Amazonian tropical moist forest');
  const [areaHa, setAreaHa] = useState('246829');
  const [startYear, setStartYear] = useState('2010-01-01');
  const [endYear, setEndYear] = useState('2039-12-31');
  const [claimedCredits, setClaimedCredits] = useState('4500000');
  const [indicator, setIndicator] = useState('ndvi');
  const [preStart, setPreStart] = useState('2002');
  const [preEnd, setPreEnd] = useState('2009');
  const [postStart, setPostStart] = useState('2010');
  const [postEnd, setPostEnd] = useState('2022');
  const [boundaryGeojson, setBoundaryGeojson] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applyPreset(p: Preset) {
    setName(p.name);
    setStandard(p.standard);
    setRegistryId(p.registry_id);
    setCountry(p.country);
    setEcosystem(p.ecosystem);
    setAreaHa(String(p.area_ha));
    setStartYear(p.crediting_period_start);
    setEndYear(p.crediting_period_end);
    setClaimedCredits(String(p.claimed_credits_tco2e));
    setIndicator(p.indicator);
    setPreStart(String(p.pre_start));
    setPreEnd(String(p.pre_end));
    setPostStart(String(p.post_start));
    setPostEnd(String(p.post_end));
    setBoundaryGeojson('');
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !country.trim() || !registryId.trim()) {
      setError('Please fill in all required fields.');
      return;
    }
    const area = parseFloat(areaHa);
    if (isNaN(area) || area <= 0) {
      setError('Project area must be a positive number in hectares.');
      return;
    }

    let parsedGeojson: Record<string, unknown> | null = null;
    if (boundaryGeojson.trim()) {
      try {
        parsedGeojson = JSON.parse(boundaryGeojson);
      } catch {
        setError('Boundary GeoJSON is invalid JSON format.');
        return;
      }
    }

    setLoading(true);
    setError(null);

    const payload = {
      name: name.trim(),
      standard: standard.trim(),
      registry_id: registryId.trim(),
      country: country.trim(),
      ecosystem: ecosystem.trim(),
      area_ha: area,
      crediting_period_start: startYear.trim(),
      crediting_period_end: endYear.trim(),
      claimed_credits_tco2e: claimedCredits.trim() ? parseFloat(claimedCredits) : null,
      indicator,
      pre_start: parseInt(preStart, 10) || 2005,
      pre_end: parseInt(preEnd, 10) || 2014,
      post_start: parseInt(postStart, 10) || 2015,
      post_end: parseInt(postEnd, 10) || 2022,
      boundary_geojson: parsedGeojson,
    };

    try {
      const res = await fetch(`${getApiBaseUrl()}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const data = await res.json();
        router.push(`/cases/${encodeURIComponent(data.case_id)}`);
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || 'Could not create project. Ensure you are signed in.');
        setLoading(false);
      }
    } catch {
      setError('Network error: Unable to reach analysis service.');
      setLoading(false);
    }
  }

  return (
    <div className={`gt-container ${styles.wrap}`}>
      <header className={styles.header}>
        <h1 className={styles.title}>Ingest Real Carbon Project</h1>
        <p className={styles.intro}>
          Register any voluntary carbon market or restoration project for independent causal screening.
          The platform will configure its donor search region, calibrate comparable non-treated control areas, and fit an empirical synthetic twin.
        </p>
      </header>

      <div className={styles.presetBar}>
        <span className={styles.presetLabel}>Quick presets:</span>
        {PRESETS.map((p) => (
          <button
            key={p.registry_id}
            type="button"
            className={styles.presetBtn}
            onClick={() => applyPreset(p)}
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          className={styles.presetBtn}
          onClick={() => {
            setName('');
            setStandard('VCS');
            setRegistryId('');
            setCountry('');
            setEcosystem('');
            setAreaHa('');
            setClaimedCredits('');
            setBoundaryGeojson('');
            setError(null);
          }}
        >
          Blank / Custom
        </button>
      </div>

      <form className={styles.form} onSubmit={handleSubmit}>
        {error && <div className={styles.error} role="alert">{error}</div>}

        <div className={styles.field}>
          <label className={styles.label} htmlFor="proj-name">Project Name *</label>
          <input
            id="proj-name"
            className={styles.input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Alto Mayo Protected Forest REDD+ Project"
            required
          />
        </div>

        <div className={styles.grid2}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-std">Carbon Standard *</label>
            <select
              id="proj-std"
              className={styles.select}
              value={standard}
              onChange={(e) => setStandard(e.target.value)}
            >
              <option value="VCS">Verra (VCS)</option>
              <option value="GoldStandard">Gold Standard</option>
              <option value="PlanVivo">Plan Vivo</option>
              <option value="ACR">American Carbon Registry (ACR)</option>
              <option value="CAR">Climate Action Reserve (CAR)</option>
            </select>
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-reg">Registry ID *</label>
            <input
              id="proj-reg"
              className={styles.input}
              value={registryId}
              onChange={(e) => setRegistryId(e.target.value)}
              placeholder="e.g. VCS 1396 or GS 4175"
              required
            />
          </div>
        </div>

        <div className={styles.grid2}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-country">Country *</label>
            <input
              id="proj-country"
              className={styles.input}
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="e.g. Peru, Kenya, Cambodia"
              required
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-eco">Ecosystem / Biome *</label>
            <input
              id="proj-eco"
              className={styles.input}
              value={ecosystem}
              onChange={(e) => setEcosystem(e.target.value)}
              placeholder="e.g. tropical peatland, miombo woodland"
              required
            />
          </div>
        </div>

        <div className={styles.grid2}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-area">Forested / Accounting Area (hectares) *</label>
            <input
              id="proj-area"
              type="number"
              className={styles.input}
              value={areaHa}
              onChange={(e) => setAreaHa(e.target.value)}
              placeholder="e.g. 182000"
              required
            />
            <p className={styles.hint}>The verified forested area claimed in the project description document.</p>
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="proj-credits">Claimed Credits (tCO2e)</label>
            <input
              id="proj-credits"
              type="number"
              className={styles.input}
              value={claimedCredits}
              onChange={(e) => setClaimedCredits(e.target.value)}
              placeholder="e.g. 5000000"
            />
            <p className={styles.hint}>Total carbon credits issued or expected across the monitoring window.</p>
          </div>
        </div>

        <div className={styles.grid2}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="cred-start">Crediting Start Date</label>
            <input
              id="cred-start"
              className={styles.input}
              value={startYear}
              onChange={(e) => setStartYear(e.target.value)}
              placeholder="YYYY-MM-DD"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="cred-end">Crediting End Date</label>
            <input
              id="cred-end"
              className={styles.input}
              value={endYear}
              onChange={(e) => setEndYear(e.target.value)}
              placeholder="YYYY-MM-DD"
            />
          </div>
        </div>

        <div className={styles.grid3}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="ind-type">Satellite Indicator</label>
            <select
              id="ind-type"
              className={styles.select}
              value={indicator}
              onChange={(e) => setIndicator(e.target.value)}
            >
              <option value="ndvi">NDVI (Normalized Difference Vegetation Index)</option>
              <option value="evi">EVI (Enhanced Vegetation Index)</option>
              <option value="nbr">NBR (Normalized Burn Ratio)</option>
            </select>
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="pre-window">Pre-Period (Fit)</label>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <input
                id="pre-window"
                type="number"
                className={styles.input}
                value={preStart}
                onChange={(e) => setPreStart(e.target.value)}
                style={{ width: '50%' }}
              />
              <span>to</span>
              <input
                type="number"
                className={styles.input}
                value={preEnd}
                onChange={(e) => setPreEnd(e.target.value)}
                style={{ width: '50%' }}
              />
            </div>
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="post-window">Post-Period (Evaluation)</label>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <input
                id="post-window"
                type="number"
                className={styles.input}
                value={postStart}
                onChange={(e) => setPostStart(e.target.value)}
                style={{ width: '50%' }}
              />
              <span>to</span>
              <input
                type="number"
                className={styles.input}
                value={postEnd}
                onChange={(e) => setPostEnd(e.target.value)}
                style={{ width: '50%' }}
              />
            </div>
          </div>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="proj-geom">Boundary GeoJSON (Optional)</label>
          <textarea
            id="proj-geom"
            className={styles.textarea}
            value={boundaryGeojson}
            onChange={(e) => setBoundaryGeojson(e.target.value)}
            placeholder='Paste a GeoJSON FeatureCollection or Polygon from Verra registry. If left blank, a representative spatial multi-polygon is automatically constructed.'
          />
        </div>

        <div className={styles.actions}>
          <LinkButton variant="ghost" href="/cases">
            Cancel
          </LinkButton>
          <Button type="submit" loading={loading}>
            Create & Verify Project
          </Button>
        </div>
      </form>
    </div>
  );
}

