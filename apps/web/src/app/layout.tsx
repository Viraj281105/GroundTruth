import React from 'react';
import type { Metadata } from 'next';
import '../styles/globals.css';
import { AppHeader } from '../components/layout/AppHeader';
import { SimulatedBanner } from '../components/ui/SimulatedBanner';

export const metadata: Metadata = {
  title: 'GroundTruth — Independent Causal Verification for Climate Restoration',
  description:
    'Evidence-based causal impact verification for carbon-credit and ecosystem restoration projects. Generates verified evidence bundles with complete provenance.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {/* UNMISSABLE, NON-DISMISSIBLE SIMULATED DATA BANNER (Strict Rule 1) */}
        <SimulatedBanner />

        {/* Global Navigation Header */}
        <AppHeader />

        {/* Main Application Content */}
        <main className="gt-main-content">{children}</main>

        {/* Scientific Grounding Footer */}
        <footer style={{
          borderTop: '1px solid var(--gt-border-subtle)',
          padding: '32px 20px',
          marginTop: '64px',
          backgroundColor: 'var(--gt-bg-surface)',
          fontSize: '12px',
          color: 'var(--gt-text-subtle)',
        }}>
          <div className="gt-container" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <strong style={{ color: 'var(--gt-text-secondary)' }}>GroundTruth Causal Impact Verifier</strong>
                <p style={{ marginTop: '2px' }}>
                  An open, reproducible screening and decision-support system. Benchmarked against third-party registry investigations.
                </p>
              </div>
              <div style={{ fontFamily: 'var(--gt-font-mono)', fontSize: '11px', color: 'var(--gt-text-muted)' }}>
                CONTRACT: v0.2.0 · ENGINE: v0.2.0 · SOLVER: FISTA
              </div>
            </div>
            <div style={{
              borderTop: '1px solid var(--gt-border-subtle)',
              paddingTop: '12px',
              display: 'flex',
              gap: '24px',
              flexWrap: 'wrap',
              fontSize: '11px',
              color: 'var(--gt-text-muted)'
            }}>
              <span>• NDVI is not carbon stock</span>
              <span>• Observed change is not causal effect without identifying assumptions</span>
              <span>• Model divergence is a trigger for accredited review, never a finding of fraud</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
