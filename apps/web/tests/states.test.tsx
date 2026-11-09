import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ErrorState, LoadingState } from '../src/components/ds/States';

/**
 * The two optional props added for issue #40. Without them both components
 * render exactly as before, so every existing use is unchanged.
 */

describe('ErrorState', () => {
  it('shows the error code and the remediation when given', () => {
    const html = renderToStaticMarkup(
      <ErrorState
        message="No database is configured, so stored runs are not available."
        code="store_not_configured"
        remediation="Set DATABASE_URL and run the migrations."
      />,
    );
    expect(html).toContain('store_not_configured');
    expect(html).toContain('Remediation Guidance:');
    expect(html).toContain('Set DATABASE_URL and run the migrations.');
  });

  it('renders as before without them', () => {
    const html = renderToStaticMarkup(<ErrorState message="Execution failed." />);
    expect(html).toContain('System Error Encountered');
    expect(html).toContain('Execution failed.');
    expect(html).not.toContain('Remediation Guidance:');
  });
});

describe('LoadingState', () => {
  it('shows only the stages it is given, in their observed states', () => {
    const html = renderToStaticMarkup(
      <LoadingState
        stages={[
          { id: 'claim', label: '1. CLAIMED BY A WORKER', desc: 'Done in 12 ms', state: 'done' },
          { id: 'engine', label: '2. RUNNING THE ANALYSIS ENGINE', desc: 'In progress for 2.3 s', state: 'active' },
        ]}
      />,
    );
    expect(html).toContain('1. CLAIMED BY A WORKER');
    expect(html).toContain('In progress for 2.3 s');
    expect(html).toContain('PROCESSING'); // the active stage only
    expect(html).not.toContain('INGESTING OBSERVATIONS'); // no illustrative stage leaks in
  });

  it('shows no stage tracker at all for an empty list', () => {
    const html = renderToStaticMarkup(<LoadingState message="Working" stages={[]} />);
    expect(html).toContain('Working');
    expect(html).not.toContain('PROCESSING');
    expect(html).not.toContain('INGESTING OBSERVATIONS');
  });

  it('keeps the illustrative tracker when no stages are given', () => {
    const html = renderToStaticMarkup(<LoadingState />);
    expect(html).toContain('1. INGESTING OBSERVATIONS');
    expect(html).toContain('9. ASSEMBLING EVIDENCE');
  });
});
