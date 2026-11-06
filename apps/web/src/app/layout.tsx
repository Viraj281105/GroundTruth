import React from 'react';
import type { Metadata, Viewport } from 'next';
import { Fraunces, Inter, IBM_Plex_Mono } from 'next/font/google';
import '../styles/globals.css';
import { AppShell } from '../components/shell/AppShell';
import { ThemeProvider } from '../lib/theme';
import { LensProvider } from '../lib/lens';
import { ToastProvider } from '../components/ds/Overlay';
import { themeInitScript } from '../lib/theme-core';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const fraunces = Fraunces({ subsets: ['latin'], variable: '--font-fraunces', display: 'swap' });
const plexMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500'], variable: '--font-plex-mono', display: 'swap' });

export const metadata: Metadata = {
  title: { default: 'GroundTruth — Independent causal verification', template: '%s · GroundTruth' },
  description:
    'Independent causal screening of carbon-credit and ecosystem restoration claims, with full provenance. Every number is traceable; divergence is a reason for review, never a finding of wrongdoing.',
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#fbf9f5' },
    { media: '(prefers-color-scheme: dark)', color: '#0d1210' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        {/* Sets data-theme before first paint so dark-mode visitors never see a light flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <ThemeProvider>
          <LensProvider>
            <ToastProvider>
              <AppShell>{children}</AppShell>
            </ToastProvider>
          </LensProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
