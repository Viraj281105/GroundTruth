'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileSearch,
  HelpCircle,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { Button, Chip } from '../ds';
import { ClaimForm } from '../../features/projects/ClaimForm';
import { createClaim, patchClaim, withdrawClaim } from '../../features/projects/claims.client';
import {
  EDIT_BLOCKED,
  correctionNotice,
  emptyForm,
  formFromSource,
  outcomeCopy,
  type ClaimKindView,
  type ClaimSource,
} from '../../features/projects/claims.model';
import { humanize, isSimulated, type ClaimStatus, type ClaimView, type PortfolioView } from './claimWorkbenchModel';
import styles from './ClaimVerificationWorkbench.module.css';

interface WorkbenchProps {
  projectName: string;
  /** The org and project slugs build the links to the project's other tabs. */
  orgSlug: string;
  projectSlug: string;
  portfolio: PortfolioView;
  /** Needed to add, correct or withdraw claims. Without it the workbench is read-only. */
  projectId?: string;
  /** Owner-level access AND an org role that may edit. */
  canEdit?: boolean;
  /** The claim types the API accepts. */
  kinds?: ClaimKindView[];
}

const STATUS_LABEL: Record<ClaimStatus, string> = {
  supported: 'Supported',
  partially_supported: 'Partially supported',
  contradicted: 'Contradicted',
  unverified: 'Unverified',
};

function statusIcon(status: ClaimStatus) {
  switch (status) {
    case 'supported':
      return <CheckCircle2 size={16} className={styles.iconSupported} aria-hidden="true" />;
    case 'partially_supported':
      return <AlertTriangle size={16} className={styles.iconPartial} aria-hidden="true" />;
    case 'contradicted':
      return <XCircle size={16} className={styles.iconContradicted} aria-hidden="true" />;
    default:
      return <HelpCircle size={16} className={styles.iconUnverified} aria-hidden="true" />;
  }
}

function gradeClass(grade: string) {
  switch (grade) {
    case 'A':
      return styles.gradeA;
    case 'B':
      return styles.gradeB;
    case 'C':
      return styles.gradeC;
    default:
      return styles.gradeD;
  }
}

function SimulatedNotice({ portfolio }: { portfolio: PortfolioView }) {
  if (!isSimulated(portfolio)) return null;
  return (
    <div className={styles.simBanner} role="status" data-data-mode="simulated">
      <Chip tone="sim">Simulated</Chip>
      <span>
        {portfolio.notice ??
          'This project’s claims are a simulated demonstration. The figures illustrate the method and are not findings about a real project.'}
      </span>
    </div>
  );
}

function List({ items, empty, className }: { items: string[]; empty: string; className?: string }) {
  if (items.length === 0) return <ul className={styles.tagList}><li className={styles.tagEmpty}>{empty}</li></ul>;
  return (
    <ul className={styles.tagList}>
      {items.map((t, i) => (
        <li key={i} className={className}>{t}</li>
      ))}
    </ul>
  );
}

/** What is missing and what to do, shown when the project has no claims to verify. */
export function ClaimsEmptyState({ portfolio, orgSlug, projectSlug }: { portfolio: PortfolioView; orgSlug: string; projectSlug: string }) {
  const base = `/app/${orgSlug}/projects/${projectSlug}`;
  return (
    <section className={styles.emptyState} aria-label="No claims to verify yet" data-testid="claims-empty">
      <h3 className={styles.emptyTitle}>No claims to verify yet</h3>
      <p className={styles.emptyLead}>
        No claims have been added to this project, so nothing is graded and no verification figures are shown. Add claims by promoting
        statements from an uploaded document (use <Link href={`${base}/evidence`} className={styles.emptyLink}>View extracted statements in the Evidence tab</Link>),
        or by typing one in below.
        Overall portfolio grade: <strong>{portfolio.overallGrade || 'N/A'}</strong>.
      </p>
      {portfolio.missingInformation.length > 0 && (
        <>
          <h4 className={styles.sectionLabel}>What is missing</h4>
          <ul className={styles.missingList}>
            {portfolio.missingInformation.map((m) => (
              <li key={m.id} className={styles.missingItem} data-status={m.status}>
                <span className={styles.missingHead}>
                  <strong>{m.label}</strong>
                  <Chip tone={m.status === 'unavailable' ? 'caution' : 'neutral'}>
                    {m.status === 'unavailable' ? 'Unavailable' : 'Not met'}
                  </Chip>
                </span>
                {m.detail && <span className={styles.missingDetail}>{m.detail}</span>}
                {m.action && <span className={styles.missingAction}>Next: {m.action}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {portfolio.nextSteps.length > 0 && (
        <>
          <h4 className={styles.sectionLabel}>Next steps</h4>
          <ol className={styles.nextSteps}>
            {portfolio.nextSteps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </>
      )}
      <nav className={styles.emptyLinks} aria-label="Where to add the missing information">
        <Link href={`${base}/evidence`} className={styles.emptyLink}>Upload documents in the Evidence tab</Link>
        <Link href={`${base}/observation`} className={styles.emptyLink}>Observations</Link>
        <Link href={`${base}/overview`} className={styles.emptyLink}>Project overview</Link>
      </nav>
    </section>
  );
}

export function ClaimVerificationWorkbench({ projectName, orgSlug, projectSlug, portfolio, projectId, canEdit = false, kinds = [] }: WorkbenchProps) {
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [expandedClaim, setExpandedClaim] = useState<string | null>(portfolio.claims[0]?.id ?? null);

  const claims = portfolio.claims;
  const filtered = claims.filter((c) => filterStatus === 'all' || c.status === filterStatus);
  const counts = portfolio.counts;

  return (
    <div className={styles.workbench} role="region" aria-label="Structured Claim Verification Workbench">
      <SimulatedNotice portfolio={portfolio} />

      <div className={styles.auditCallout}>
        <div className={styles.auditCalloutHeader}>
          <ShieldAlert size={18} className={styles.auditAlertIcon} aria-hidden="true" />
          <strong>Claim verification for {projectName || 'this project'}</strong>
        </div>
        <p>
          Each claim is split into individually testable statements, so one metric without evidence does not turn the
          whole project inconclusive. Vegetation greening is never equated with causal restoration success. A claim marked
          unverified means the evidence needed to test it has not been supplied, not that it is false.
        </p>
        {portfolio.guardrails.length > 0 && (
          <ul className={styles.guardrails}>
            {portfolio.guardrails.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        )}
      </div>

      {!portfolio.hasClaims ? (
        <>
          <ClaimsEmptyState portfolio={portfolio} orgSlug={orgSlug} projectSlug={projectSlug} />
          <AddClaimByTyping projectId={projectId} canEdit={canEdit} kinds={kinds} />
        </>
      ) : (
        <>
          <div className={styles.kpiRow}>
            <div className={styles.kpiCard}>
              <span className={styles.kpiLabel}>Claims assessed</span>
              <span className={styles.kpiValue}>{claims.length}</span>
              <span className={styles.kpiSub}>Portfolio grade {portfolio.overallGrade || 'N/A'}</span>
            </div>
            <div className={`${styles.kpiCard} ${styles.kpiCardSupported}`}>
              <span className={styles.kpiLabel}>Supported</span>
              <span className={styles.kpiValue}>{counts.supported}</span>
            </div>
            <div className={`${styles.kpiCard} ${styles.kpiCardPartial}`}>
              <span className={styles.kpiLabel}>Partially supported</span>
              <span className={styles.kpiValue}>{counts.partially_supported}</span>
            </div>
            <div className={`${styles.kpiCard} ${styles.kpiCardContradicted}`}>
              <span className={styles.kpiLabel}>Contradicted</span>
              <span className={styles.kpiValue}>{counts.contradicted}</span>
            </div>
            <div className={`${styles.kpiCard} ${styles.kpiCardUnverified}`}>
              <span className={styles.kpiLabel}>Unverified</span>
              <span className={styles.kpiValue}>{counts.unverified}</span>
            </div>
          </div>

          <div className={styles.filterBar} role="tablist" aria-label="Filter claims by status">
            {(['all', 'supported', 'partially_supported', 'contradicted', 'unverified'] as const).map((s) => (
              <button
                key={s}
                type="button"
                role="tab"
                aria-selected={filterStatus === s}
                className={`${styles.filterBtn} ${filterStatus === s ? styles.filterBtnActive : ''}`}
                onClick={() => setFilterStatus(s)}
              >
                {s === 'all' ? `All claims (${claims.length})` : `${STATUS_LABEL[s]} (${counts[s]})`}
              </button>
            ))}
          </div>

          <AddClaimByTyping projectId={projectId} canEdit={canEdit} kinds={kinds} />

          <div className={styles.claimsList}>
            {filtered.map((claim) => (
              <ClaimCard
                key={claim.id}
                claim={claim}
                projectId={projectId}
                canEdit={canEdit}
                kinds={kinds}
                simulated={isSimulated(portfolio)}
                expanded={expandedClaim === claim.id}
                onToggle={() => setExpandedClaim((cur) => (cur === claim.id ? null : claim.id))}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Grade({ label, grade, score }: { label: string; grade: string; score: number | null }) {
  return (
    <div className={styles.gradeBadge} title={score === null ? label : `${label}: score ${score}`}>
      <span className={styles.gradeType}>{label}</span>
      <span className={`${styles.gradeLetter} ${gradeClass(grade)}`}>{grade || 'N/A'}</span>
    </div>
  );
}

function ClaimCard({
  claim,
  simulated,
  expanded,
  onToggle,
  projectId,
  canEdit,
  kinds,
}: {
  claim: ClaimView;
  simulated: boolean;
  expanded: boolean;
  onToggle: () => void;
  projectId?: string;
  canEdit: boolean;
  kinds: ClaimKindView[];
}) {
  const g = claim.grading;
  const src = claim.source;
  const outcome = src ? outcomeCopy(claim.status.toUpperCase()) : null;
  return (
    <div className={`${styles.claimCard} ${styles[`card_${claim.status}`]}`}>
      <div
        className={styles.claimHeader}
        onClick={onToggle}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
        aria-expanded={expanded}
      >
        <div className={styles.claimTitleGroup}>
          <div className={styles.claimMetaRow}>
            <span className={styles.claimId}>{claim.id}</span>
            <span className={`${styles.statusChip} ${styles[`chip_${claim.status}`]}`}>
              {statusIcon(claim.status)}
              <span>{outcome ? outcome.label.toUpperCase() : STATUS_LABEL[claim.status].toUpperCase()}</span>
            </span>
            {claim.kind && <span className={styles.claimKindTag}>{humanize(claim.kind)}</span>}
            {simulated && <Chip tone="sim">Simulated</Chip>}
          </div>
          <h3 className={styles.claimName}>{claim.title}</h3>
          <div className={styles.statedValRow}>
            <span className={styles.statedLabel}>Stated claim:</span>
            <strong className={styles.statedValue}>
              {claim.claimedValue ? `${claim.claimedValue} ${claim.claimedUnit}`.trim() : 'No value stated'}
            </strong>
          </div>
          {claim.observedValue && (
            <div className={styles.statedValRow}>
              <span className={styles.statedLabel}>Observed:</span>
              <strong className={styles.statedValue}>{`${claim.observedValue} ${claim.observedUnit}`.trim()}</strong>
              {claim.discrepancyPercentage !== null && (
                <span className={styles.statedLabel}>({claim.discrepancyPercentage}% difference)</span>
              )}
            </div>
          )}
        </div>

        <div className={styles.gradeMiniWrap}>
          {!src && <Grade label="EV. QUAL" grade={g.evidenceQuality} score={g.evidenceQualityScore} />}
          {!src && <Grade label="METHOD" grade={g.methodological} score={g.methodologicalScore} />}
          {!src && <Grade label="CAUSAL" grade={g.causal} score={g.causalScore} />}
          <div className={styles.chevronWrap}>{expanded ? <ChevronUp size={20} aria-hidden="true" /> : <ChevronDown size={20} aria-hidden="true" />}</div>
        </div>
      </div>

      {expanded && (
        <div className={styles.claimBody}>
          {src && <SourceBlock source={src} />}
          {src && outcome && <OutcomeBlock claim={claim} plain={outcome.plain} />}
          {src && <ClaimControls claimId={claim.id} source={src} projectId={projectId} canEdit={canEdit} kinds={kinds} />}
          {claim.definition && (
            <div className={styles.definitionBox}>
              <span className={styles.sectionLabel}>Definition and scope:</span>
              <p>{claim.definition}</p>
            </div>
          )}

          {(!src || claim.statements.length > 0) && (
          <div className={styles.statementsBox}>
            <span className={styles.sectionLabel}>Testable statements:</span>
            {claim.statements.length === 0 ? (
              <p className={styles.methodText}>No statements were decomposed for this claim.</p>
            ) : (
              <ul className={styles.statementList}>
                {claim.statements.map((s) => (
                  <li key={s.id} className={styles.statementItem}>
                    <span className={styles.statementId}>{s.id}</span>
                    <span className={styles.statementText}>{s.text}</span>
                    <span className={styles.statementTarget}>
                      [{s.targetMetric || 'metric not named'}
                      {s.claimedValue ? ` · claimed ${s.claimedValue}` : ''}
                      {s.observedValue ? ` · observed ${s.observedValue}` : ' · no observed value'}
                      {s.status ? ` · ${humanize(s.status)}` : ''}]
                    </span>
                    {s.rationale && <span className={styles.statementTarget}>{s.rationale}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          )}

          <div className={styles.evidenceGrid}>
            <div className={styles.evidenceCol}>
              <span className={styles.colHeaderPositive}>
                <ShieldCheck size={14} aria-hidden="true" />
                Required vs available evidence
              </span>
              <div className={styles.evidenceGroup}>
                <span className={styles.subColLabel}>Required:</span>
                <List items={claim.requiredEvidence} empty="None listed" className={styles.tagRequired} />
                <span className={styles.subColLabel}>Available:</span>
                <List items={claim.availableEvidence} empty="No evidence available" className={styles.tagAvailable} />
                <span className={styles.subColLabel}>Missing:</span>
                <List items={claim.missing} empty="None listed" className={styles.tagContradictory} />
              </div>
            </div>

            <div className={styles.evidenceCol}>
              <span className={styles.colHeaderObservations}>
                <FileSearch size={14} aria-hidden="true" />
                Supporting vs contradictory observations
              </span>
              <div className={styles.evidenceGroup}>
                <span className={styles.subColLabel}>Supporting:</span>
                <List items={claim.supporting} empty="No verifiable supporting data" className={styles.tagSupporting} />
                <span className={styles.subColLabel}>Contradictory / deficiencies:</span>
                <List items={claim.contradictory} empty="None reported" className={styles.tagContradictory} />
              </div>
            </div>
          </div>

          <div className={styles.methodologyBox}>
            <div className={styles.methodCol}>
              <span className={styles.sectionLabel}>Verification methodology:</span>
              <p className={styles.methodText}>{claim.methodology || 'Not stated.'}</p>
            </div>
            <div className={styles.methodCol}>
              <span className={styles.sectionLabel}>Confidence and limitations:</span>
              {claim.limitations.length === 0 ? (
                <p className={styles.methodText}>Not stated.</p>
              ) : (
                <ul className={styles.methodList}>
                  {claim.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {!src && g.rationale.length > 0 && (
            <div className={styles.definitionBox}>
              <span className={styles.sectionLabel}>Grading rationale (overall grade {g.overall || 'N/A'}):</span>
              <ul className={styles.methodList}>
                {g.rationale.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {claim.correctiveAction && (
            <div className={styles.definitionBox}>
              <span className={styles.sectionLabel}>Suggested follow-up:</span>
              <p>{claim.correctiveAction}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Where a promoted or typed claim came from, and what was corrected. The original wording is never edited. */
export function SourceBlock({ source }: { source: ClaimSource }) {
  const notice = correctionNotice(source);
  return (
    <section className={styles.sourceBox} aria-label="Where this claim came from" data-claim-source>
      <span className={styles.sectionLabel}>Where this claim came from</span>
      {source.document_id ? (
        <p className={styles.methodText}>
          Document: <strong>{source.document_name ?? 'a project document'}</strong>
        </p>
      ) : (
        <p className={styles.methodText}>Typed in by a team member (not taken from a document).</p>
      )}
      <p className={styles.sourceQuote}>
        {source.document_id ? 'The document said: ' : 'As typed: '}&ldquo;{source.original_text}&rdquo;
      </p>
      {notice && (
        <div className={styles.correction} data-claim-edited>
          <p className={styles.methodText}>
            <strong>{notice}</strong>
          </p>
          <p className={styles.sourceQuote}>Now tested as: &ldquo;{source.statement_text}&rdquo;</p>
        </div>
      )}
    </section>
  );
}

function OutcomeBlock({ claim, plain }: { claim: ClaimView; plain: string }) {
  return (
    <section className={styles.outcomeBox} aria-label="How this claim matches the evidence" data-claim-outcome={claim.status}>
      <span className={styles.sectionLabel}>How it matches the evidence</span>
      {claim.headline && <p className={styles.outcomeHeadline}>{claim.headline}</p>}
      <p className={styles.methodText}>{plain}</p>
      {claim.reasons.length > 0 && (
        <>
          <span className={styles.subColLabel}>Why:</span>
          <ul className={styles.methodList}>
            {claim.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** Edit and Withdraw for one claim. Editors only; everyone else gets a plain explanation. */
function ClaimControls({ claimId, source, projectId, canEdit, kinds }: { claimId: string; source: ClaimSource; projectId?: string; canEdit: boolean; kinds: ClaimKindView[] }) {
  const router = useRouter();
  const [mode, setMode] = useState<'idle' | 'edit' | 'confirm'>('idle');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canEdit || !projectId) {
    return (
      <p className={styles.methodText} data-claim-readonly>
        {EDIT_BLOCKED}
      </p>
    );
  }

  async function onWithdraw() {
    setBusy(true);
    setError(null);
    const r = await withdrawClaim(projectId as string, claimId);
    setBusy(false);
    if (!r.ok) return setError(r.message);
    setMode('idle');
    router.refresh();
  }

  if (mode === 'edit') {
    return (
      <ClaimForm
        idPrefix={`edit-${claimId}`}
        initial={formFromSource(source)}
        kinds={kinds}
        submitLabel="Save correction"
        busy={busy}
        error={error}
        onCancel={() => {
          setMode('idle');
          setError(null);
        }}
        intro={<p className={styles.methodText}>The original wording above stays as it is. Your correction changes only what is tested.</p>}
        onSubmit={async (fields) => {
          setBusy(true);
          setError(null);
          const r = await patchClaim(projectId, claimId, fields);
          setBusy(false);
          if (!r.ok) return setError(r.message);
          setMode('idle');
          router.refresh();
        }}
      />
    );
  }

  return (
    <div className={styles.controls}>
      {mode === 'confirm' ? (
        <>
          <p className={styles.methodText}>Withdraw this claim? It stops being tested and leaves this list. The record that it was added is kept.</p>
          <Button variant="danger" size="sm" loading={busy} onClick={onWithdraw}>
            Withdraw claim
          </Button>
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => setMode('idle')}>
            Keep it
          </Button>
        </>
      ) : (
        <>
          <Button variant="secondary" size="sm" onClick={() => setMode('edit')}>
            Edit
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setMode('confirm')}>
            Withdraw
          </Button>
        </>
      )}
      {error && (
        <p role="alert" className={styles.methodText}>
          {error}
        </p>
      )}
    </div>
  );
}

/** Add a claim by typing it. Typed claims are tested the same way as claims taken from documents. */
export function AddClaimByTyping({ projectId, canEdit, kinds }: { projectId?: string; canEdit: boolean; kinds: ClaimKindView[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (!canEdit || !projectId) {
    return (
      <p className={styles.methodText} data-claim-readonly>
        {EDIT_BLOCKED}
      </p>
    );
  }
  if (!open) {
    return (
      <div className={styles.controls}>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            setOpen(true);
            setDone(false);
          }}
        >
          Add a claim by typing it
        </Button>
        {done && (
          <span role="status" className={styles.methodText}>
            Claim added. It is now compared with the evidence on file.
          </span>
        )}
      </div>
    );
  }
  return (
    <section className={styles.sourceBox} aria-label="Add a claim by typing it">
      <span className={styles.sectionLabel}>Add a claim by typing it</span>
      <ClaimForm
        idPrefix="typed"
        initial={emptyForm()}
        kinds={kinds}
        submitLabel="Add claim"
        busy={busy}
        error={error}
        intro={<p className={styles.methodText}>Type a claim someone has made about this project. Adding it does not verify it; it is compared with the evidence on file.</p>}
        onCancel={() => {
          setOpen(false);
          setError(null);
        }}
        onSubmit={async (fields) => {
          setBusy(true);
          setError(null);
          const r = await createClaim(projectId, fields);
          setBusy(false);
          if (!r.ok) return setError(r.message);
          setOpen(false);
          setDone(true);
          router.refresh();
        }}
      />
    </section>
  );
}
