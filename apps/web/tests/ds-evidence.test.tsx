import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { EvidenceStateBadge, type EvidenceState } from '../src/components/ds/EvidenceStateBadge';
import { DataModeBanner } from '../src/components/ds/DataModeBanner';
import { UnavailablePanel } from '../src/components/ds/UnavailablePanel';
import { StatusChip, DIMENSION_STATUSES } from '../src/components/ds/StatusChip';
import { t } from '../src/lib/i18n';

const STATES: EvidenceState[] = ['OBSERVED', 'DERIVED', 'MODEL_ESTIMATED', 'INFERRED', 'UNAVAILABLE'];

const html = (el: React.ReactElement) => renderToStaticMarkup(el);
const label = (m: string) => /aria-label="([^"]*)"/.exec(m)?.[1];

describe('EvidenceStateBadge', () => {
  it.each(STATES)('exposes an accessible label for %s', (state) => {
    const m = html(<EvidenceStateBadge state={state} />);
    expect(m).toContain('role="img"');
    expect(label(m)).toMatch(/^Evidence state: /);
    expect(m).toContain(`data-evidence-state="${state}"`);
  });

  it('labels are distinct per state', () => {
    const labels = STATES.map((s) => label(html(<EvidenceStateBadge state={s} />)));
    expect(new Set(labels).size).toBe(STATES.length);
  });
});

describe('DataModeBanner', () => {
  it('renders nothing for observed', () => {
    expect(html(<DataModeBanner mode="observed" />)).toBe('');
  });
  it('shows the existing simulated copy for simulated', () => {
    const m = html(<DataModeBanner mode="simulated" />);
    expect(m).toContain('>Simulated data<');
    expect(m).toContain(t('sim.explain'));
    expect(m).toContain('role="status"');
  });
});

describe('UnavailablePanel', () => {
  it('shows title, reason, evidenceNeeded and the optional action', () => {
    const m = html(
      <UnavailablePanel
        title="Field tasks"
        reason="No field data has been collected."
        evidenceNeeded="Signed field-visit records with GPS."
        action={<button>Request</button>}
      />,
    );
    expect(m).toContain('Field tasks');
    expect(m).toContain('No field data has been collected.');
    expect(m).toContain('Signed field-visit records with GPS.');
    expect(m).toContain('<button>Request</button>');
  });
});

describe('UnavailablePanel without action', () => {
  it('omits the action container', () => {
    const m = html(<UnavailablePanel title="T" reason="r" evidenceNeeded="e" />);
    expect(m).not.toContain('class="UnavailablePanel_action');
    expect(m).not.toMatch(/action/);
  });
});

describe('StatusChip', () => {
  it.each(DIMENSION_STATUSES)('renders %s with an accessible name', (status) => {
    const m = html(<StatusChip status={status} />);
    expect(label(m)).toBe(`Status: ${status}`);
  });
  it('covers exactly the engine vocabulary', () => {
    expect([...DIMENSION_STATUSES]).toEqual([
      'Improving', 'Deteriorating', 'Stable', 'Mixed spatial performance',
      'Elevated ecological risk', 'No clear change', 'Insufficient evidence',
    ]);
  });
  it('never styles Insufficient evidence like Improving', () => {
    const style = (m: string) => /data-status-style="([^"]*)"/.exec(m)?.[1];
    const sa = style(html(<StatusChip status="Insufficient evidence" />));
    const sb = style(html(<StatusChip status="Improving" />));
    expect(sa).toBe('insufficient');
    expect(sa).not.toBe(sb);
    expect(sa).not.toBe('improving');
  });
});
