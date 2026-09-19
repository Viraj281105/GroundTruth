'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Badge } from '../ui/Badge';
import { Shield, Activity, Layers, Menu, X, Radio, Satellite, Compass } from 'lucide-react';
import styles from './AppHeader.module.css';

export const AppHeader: React.FC = () => {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { href: '/', label: 'Active Investigations', icon: <Layers size={14} /> },
    { href: '/health', label: 'Sensors & Engine Health', icon: <Activity size={14} /> },
  ];

  // Coordinates telemetry if inspecting Kariba case
  const isKariba = pathname.includes('kariba');

  return (
    <>
      {/* Skip to Content for Accessibility */}
      <a href="#main-content" className="gt-skip-link">
        Skip to main content
      </a>

      <header className={styles.header}>
        <div className={styles.container}>
          {/* Brand & Wordmark */}
          <Link href="/" className={styles.brand} onClick={() => setMobileMenuOpen(false)}>
            <div className={styles.brandIconWrapper}>
              <Satellite size={18} className={styles.brandIcon} />
            </div>
            <div className={styles.brandText}>
              <div className={styles.brandTitleRow}>
                <span className={styles.brandName}>GROUNDTRUTH</span>
                <span className={styles.brandSeparator}>{'//'}</span>
                <span className={styles.brandConsole}>CAUSAL OBSERVATORY</span>
              </div>
              <div className={styles.brandSubRow}>
                <span className={styles.brandSub}>Satellite-Driven Causal Verification</span>
                {isKariba && (
                  <span className={styles.coordsBadge}>
                    [17°12&apos;S, 28°45&apos;E]
                  </span>
                )}
              </div>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav className={styles.desktopNav} aria-label="Main Navigation">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Right Status Badges & Telemetry */}
          <div className={styles.headerRight}>
            <div className={styles.apiStatus} title="Sentinel-2 & Landsat Ingestion Stream">
              <span className={styles.liveDot} />
              <span className={styles.apiStatusText}>EO CONSOLE LIVE</span>
            </div>

            <Badge tone="simulated" size="sm" variant="solid" className={styles.simulatedBadge}>
              SIMULATED (FIXTURES)
            </Badge>

            {/* Mobile Hamburger Toggle */}
            <button
              type="button"
              className={styles.hamburgerBtn}
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label={mobileMenuOpen ? 'Close menu' : 'Open navigation menu'}
              aria-expanded={mobileMenuOpen}
            >
              {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className={styles.mobileDrawer}>
            <nav className={styles.mobileNav} aria-label="Mobile Navigation">
              {navItems.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`${styles.mobileNavLink} ${isActive ? styles.mobileNavLinkActive : ''}`}
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </Link>
                );
              })}
              <div className={styles.mobileDrawerFooter}>
                <span className={styles.mobileEngineNote}>
                  GroundTruth Causal Engine v0.2.0 · FISTA Simplex Solver
                </span>
              </div>
            </nav>
          </div>
        )}
      </header>
    </>
  );
};
