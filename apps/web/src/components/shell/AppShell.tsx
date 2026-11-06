import React from 'react';
import { Header } from './Header';
import { Footer } from './Footer';

/** App chrome: skip link, sticky header (with the permanent simulated-data chip), page, footer. */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a href="#main-content" className="gt-skip-link">
        Skip to main content
      </a>
      <Header />
      <main id="main-content" className="gt-main-content">
        {children}
      </main>
      <Footer />
    </>
  );
}
