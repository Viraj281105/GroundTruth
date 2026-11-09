'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { BrainCircuit, Send, ShieldAlert } from 'lucide-react';
import { Chip } from '../ds';
import { createApiClient } from '../../lib/api-client';
import {
  INTELLIGENCE_MODES,
  STAKEHOLDER_ROLES,
  httpProblem,
  latencyLabel,
  researchBody,
  statusMessage,
  toResearch,
  type ProjectOption,
  type ResearchView,
  type ServiceStatus,
} from './intelligenceModel';
import styles from './GroqIntelligenceWorkspace.module.css';

type Run = { phase: 'idle' } | { phase: 'loading' } | { phase: 'done'; result: ResearchView } | { phase: 'failed'; message: string };

/** Facts, inferences and gaps are separate sections so a reader can always tell record from model opinion. */
export function ResearchResult({ result }: { result: ResearchView }) {
  const latency = latencyLabel(result.latencyMs);
  const ok = result.status === 'ok';
  const problem = result.status !== 'ok' ? statusMessage(result) : '';
  return (
    <div className={styles.workspace} aria-live="polite" data-research-status={result.status}>
      <div className={styles.telemetryBar}>
        <span>Status: <strong>{result.status.replace(/_/g, ' ')}</strong></span>
        {result.model && <span>Model: <strong>{result.model}</strong></span>}
        {latency && <span>Measured response time: <strong>{latency}</strong></span>}
        {result.dataMode === 'synthetic' && <Chip tone="sim">Simulated</Chip>}
      </div>

      {!ok && (
        <div className={`${styles.notice} ${styles.noticeProblem}`} role="alert">
          <strong>{result.status === 'insufficient_context' ? 'Not enough project information to answer.' : 'No answer was produced.'}</strong>{' '}
          {problem}
        </div>
      )}

      {ok && result.answer && (
        <section className={styles.answer} aria-label="Answer">
          <h3 className={styles.sectionTitle}>Answer</h3>
          <p className={styles.answerText}>{result.answer}</p>
          {result.guardrailNotice && <p className={styles.disclaimerText}>{result.guardrailNotice}</p>}
        </section>
      )}

      {(ok || result.facts.length > 0 || result.missingContext.length > 0) && (
        <div className={styles.sections}>
          <section className={`${styles.section} ${styles.sectionFacts}`} aria-label="Retrieved facts">
            <h3 className={styles.sectionTitle}>Retrieved facts</h3>
            <p className={styles.sectionSub}>Recorded for this project. Each shows where it came from.</p>
            {result.facts.length === 0 ? (
              <p className={styles.empty}>No project records were retrieved for this question.</p>
            ) : (
              <ul className={styles.items}>
                {result.facts.map((f) => (
                  <li key={f.id} className={styles.item}>
                    <span>{f.statement}</span>
                    <span className={styles.itemMeta}>
                      Source: {f.source || 'not recorded'}
                      {f.kind ? ` · ${f.kind}` : ''}
                      {f.citedByModel === true ? ' · cited in the answer' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={`${styles.section} ${styles.sectionInference}`} aria-label="Model inferences">
            <h3 className={styles.sectionTitle}>Model inferences</h3>
            <p className={styles.sectionSub}>Inferences by the language model. They are not records and not verified findings.</p>
            {result.inferences.length === 0 ? (
              <p className={styles.empty}>The model made no inferences.</p>
            ) : (
              <ul className={styles.items}>
                {result.inferences.map((x, i) => (
                  <li key={i} className={styles.item}>
                    <span>
                      <Chip tone="neutral">{x.label || 'Inference'}</Chip> {x.statement}
                    </span>
                    {x.basedOn.length > 0 && <span className={styles.itemMeta}>Based on: {x.basedOn.join(', ')}</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={`${styles.section} ${styles.sectionGaps}`} aria-label="Unsupported conclusions and missing context">
            <h3 className={styles.sectionTitle}>Cannot be concluded from the records</h3>
            <p className={styles.sectionSub}>Questions the project records do not support, and the context that is missing.</p>
            <h4 className={styles.fieldLabel}>Unsupported or unanswerable</h4>
            {result.unsupported.length === 0 ? (
              <p className={styles.empty}>None listed.</p>
            ) : (
              <ul className={styles.items}>
                {result.unsupported.map((u, i) => (
                  <li key={i} className={styles.item}>{u}</li>
                ))}
              </ul>
            )}
            <h4 className={styles.fieldLabel}>Missing context</h4>
            {result.missingContext.length === 0 ? (
              <p className={styles.empty}>None listed.</p>
            ) : (
              <ul className={styles.items}>
                {result.missingContext.map((m, i) => (
                  <li key={i} className={styles.item}>{m}</li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {result.literature.length > 0 && (
        <section className={styles.literature} aria-label="Published literature">
          <h3 className={styles.sectionTitle}>Published literature (general background, not evidence about this project)</h3>
          <ul className={styles.items}>
            {result.literature.map((l, i) => (
              <li key={i} className={styles.item}>
                <strong>{l.title || 'Untitled'}</strong>
                <span className={styles.itemMeta}>
                  {[l.authors, l.venue, l.year].filter(Boolean).join(' · ')}
                  {l.doi && (
                    <>
                      {' · '}
                      <a href={`https://doi.org/${encodeURI(l.doi)}`} target="_blank" rel="noopener noreferrer">DOI {l.doi}</a>
                    </>
                  )}
                </span>
                {l.relevance && <span>{l.relevance}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {result.guardrailDropped.length > 0 && (
        <p className={styles.disclaimerText}>
          {result.guardrailDropped.length} model statement(s) were removed because they were not backed by the project records.
        </p>
      )}
    </div>
  );
}

export function GroqIntelligenceWorkspace({
  orgSlug,
  projects,
  service,
}: {
  orgSlug: string;
  projects: ProjectOption[];
  service: ServiceStatus;
}) {
  const [projectId, setProjectId] = useState<string>(projects[0]?.id ?? '');
  const [mode, setMode] = useState<string>('csr_due_diligence');
  const [role, setRole] = useState<string>('csr');
  const [query, setQuery] = useState('');
  const [run, setRun] = useState<Run>({ phase: 'idle' });

  const available = service.state === 'configured';
  const canAsk = available && projects.length > 0 && projectId !== '' && query.trim().length >= 3 && run.phase !== 'loading';

  async function ask(e?: React.FormEvent) {
    e?.preventDefault();
    if (!canAsk) return;
    setRun({ phase: 'loading' });
    try {
      const { data, response } = await createApiClient().POST('/intelligence/research', {
        body: researchBody(query, projectId, mode, role),
      });
      if (data) setRun({ phase: 'done', result: toResearch(data) });
      else setRun({ phase: 'failed', message: httpProblem(response.status) });
    } catch {
      setRun({ phase: 'failed', message: httpProblem(0) });
    }
  }

  return (
    <div className={styles.workspace}>
      <header className={styles.header}>
        <div className={styles.titleArea}>
          <span className={styles.kicker}>Environmental intelligence</span>
          <h1 className={styles.title}>Ask about a project</h1>
          <p className={styles.desc}>
            Questions are answered from the selected project&apos;s own recorded information. The language model restates and
            cautiously interprets those records; it computes no numbers and verifies nothing.
          </p>
        </div>
        <div className={styles.guardrailBanner} role="note">
          <ShieldAlert size={16} className={styles.guardrailIcon} aria-hidden="true" />
          <div className={styles.guardrailContent}>
            <strong>Scientific guardrails</strong>
            <span>
              Retrieved facts, model inferences and unsupported conclusions are shown separately. A divergence between a claim and
              the records warrants accredited review; it is not a finding about anyone.
            </span>
          </div>
        </div>
      </header>

      <div className={`${styles.statusBar} ${available ? '' : styles.statusUnavailable}`} role="status" data-service-state={service.state}>
        <BrainCircuit size={14} aria-hidden="true" />
        {service.state === 'configured' ? (
          <span>
            Intelligence service available
            {[service.provider, service.model].filter(Boolean).length > 0 ? ` (${[service.provider, service.model].filter(Boolean).join(', ')})` : ''}.
          </span>
        ) : (
          <span>
            <strong>Intelligence service unavailable.</strong> {service.reason} Questions are disabled until it is available.
          </span>
        )}
      </div>

      {projects.length === 0 ? (
        <section className={styles.emptyState} aria-label="No project context">
          <h2 className={styles.sectionTitle}>There is no project to ask about yet</h2>
          <p className={styles.desc}>
            Answers are built from a project&apos;s own records, so this organization needs at least one project first. No sample
            answer is shown.
          </p>
          <Link className={styles.emptyLink} href={`/app/${orgSlug}/projects/new`}>Create a project</Link>
        </section>
      ) : (
        <form onSubmit={ask} className={styles.workspace}>
          <div className={styles.setup}>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="intel-project">Project</label>
              <select id="intel-project" className={styles.select} value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}{p.simulated ? ' (simulated)' : ''}</option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="intel-mode">Mode</label>
              <select id="intel-mode" className={styles.select} value={mode} onChange={(e) => setMode(e.target.value)}>
                {INTELLIGENCE_MODES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
            {mode === 'stakeholder_reports' && (
              <div className={styles.field}>
                <label className={styles.fieldLabel} htmlFor="intel-role">Audience</label>
                <select id="intel-role" className={styles.select} value={role} onChange={(e) => setRole(e.target.value)}>
                  {STAKEHOLDER_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className={styles.queryBar}>
            <label htmlFor="intel-query" style={{ position: 'absolute', left: '-9999px' }}>Your question</label>
            <input
              id="intel-query"
              className={styles.queryInput}
              type="text"
              value={query}
              maxLength={1000}
              disabled={!available}
              placeholder={available ? 'Ask a question about this project’s records' : 'Unavailable: the intelligence service is not configured'}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="submit" className={styles.runBtn} disabled={!canAsk}>
              <Send size={14} aria-hidden="true" />
              {run.phase === 'loading' ? 'Asking…' : 'Ask'}
            </button>
          </div>
        </form>
      )}

      {run.phase === 'loading' && (
        <p className={styles.notice} role="status" aria-busy="true">Reading the project&apos;s records and asking the model&hellip;</p>
      )}
      {run.phase === 'failed' && (
        <div className={`${styles.notice} ${styles.noticeProblem}`} role="alert">{run.message}</div>
      )}
      {run.phase === 'done' && <ResearchResult result={run.result} />}
    </div>
  );
}
