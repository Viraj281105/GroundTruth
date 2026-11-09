import React from 'react';
import Link from 'next/link';
import { Download, ExternalLink, FileCheck, FileCode, FileText, Lock, ShieldCheck } from 'lucide-react';
import styles from './ReportsPage.module.css';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Audit Reports & CSR Dossiers — GroundTruth 2.0' };

interface ReportItem {
  id: string;
  title: string;
  type: 'audit_dossier' | 'csr_summary' | 'methodology_spec' | 'benchmark_eval';
  project_name: string;
  date: string;
  merkle_root: string;
  status: 'sealed' | 'draft';
  file_size: string;
}

const REPORTS: ReportItem[] = [
  {
    id: 'RPT-2026-KARIBA-AUDIT',
    title: 'Kariba REDD+ VCS-981 Independent Verification Audit Dossier',
    type: 'audit_dossier',
    project_name: 'Kariba REDD+ Wildlife Corridor',
    date: '2026-11-09',
    merkle_root: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    status: 'sealed',
    file_size: '4.8 MB (PDF + JSON-LD)',
  },
  {
    id: 'RPT-2026-CSR-PORTFOLIO',
    title: 'Q4 2026 CSR Sustainability & Restoration Additionality Synthesis',
    type: 'csr_summary',
    project_name: 'Southern Africa Restoration Portfolio',
    date: '2026-11-08',
    merkle_root: 'a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e',
    status: 'sealed',
    file_size: '2.4 MB (Executive Deck)',
  },
  {
    id: 'RPT-2026-SCIENTIFIC-METHOD',
    title: 'GroundTruth 2.0 Scientific Methodology & Causal Inference Protocol',
    type: 'methodology_spec',
    project_name: 'All Registered Projects',
    date: '2026-11-05',
    merkle_root: 'c5d4e3f2a1b0987654321fedcba0987654321fedcba0987654321fedcba09876',
    status: 'sealed',
    file_size: '1.2 MB (Whitepaper)',
  },
  {
    id: 'RPT-2026-BENCHMARK-SUITE',
    title: 'Independent Validation Benchmark Suite & False-Positive Calibration',
    type: 'benchmark_eval',
    project_name: 'Benchmark Evaluation Set v2.0',
    date: '2026-11-04',
    merkle_root: '9876543210abcdef0123456789abcdef9876543210abcdef0123456789abcdef',
    status: 'sealed',
    file_size: '3.1 MB (Technical Annex)',
  },
];

export default async function ReportsPage({ params }: { params: { org: string } }) {
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.kicker}>Cryptographically Sealed Findings</span>
        <h1 className={styles.title}>Audit Reports & Export History</h1>
        <p className={styles.desc}>
          Immutable verification dossiers, CSR executive briefs, and scientific reproducibility bundles. Every generated report carries a SHA-256 Merkle root binding the exact inputs, geometry, commit SHA, and analytical outputs.
        </p>
      </div>

      <div className={styles.merkleBanner}>
        <ShieldCheck size={20} className={styles.bannerIcon} />
        <div className={styles.bannerText}>
          <strong>Deterministic Reproducibility Guarantee:</strong>
          <span>
            Any third-party auditor can reproduce identical numerical findings by re-running the registered Git commit hash against the hashed input geometry.
          </span>
        </div>
      </div>

      <div className={styles.reportsGrid}>
        {REPORTS.map((r) => (
          <div key={r.id} className={styles.reportCard}>
            <div className={styles.cardHeader}>
              <div className={styles.typeRow}>
                <span className={styles.reportId}>{r.id}</span>
                <span className={styles.sealedBadge}>
                  <Lock size={11} />
                  <span>SEALED</span>
                </span>
              </div>
              <h3 className={styles.reportTitle}>{r.title}</h3>
              <span className={styles.projectName}>{r.project_name}</span>
            </div>

            <div className={styles.cardBody}>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>Published:</span>
                <span className={styles.metaVal}>{r.date}</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>Artifact Size:</span>
                <span className={styles.metaVal}>{r.file_size}</span>
              </div>
              <div className={styles.hashBox}>
                <span className={styles.hashLabel}>Merkle Root Digest:</span>
                <code className={styles.hashCode} title={r.merkle_root}>
                  {r.merkle_root.substring(0, 24)}...
                </code>
              </div>
            </div>

            <div className={styles.cardFooter}>
              <a
                href={`/api/v2/audit/ledger/${r.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.downloadBtn}
              >
                <Download size={13} />
                <span>Download Bundle</span>
              </a>
              <Link href={`/app/${params.org}/projects/kariba/reports`} className={styles.viewLink}>
                <span>Inspect Dossier</span>
                <ExternalLink size={12} />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

