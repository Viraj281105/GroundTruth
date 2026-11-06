import React from 'react';
import { Card, EmptyState } from '../../../components/ds';
import { Lens } from '../../../lib/lens';
import type { MethodModel } from './model';
import styles from './method.module.css';

export const methodCopy = {
  design: 'Study design',
  designLead: 'How this case is set up. The published reference result is never an input to the estimate.',
  pipeline: 'How the estimate is built',
  noRun: 'The method for a specific run appears once an analysis has been run for this case.',
  noRunTitle: 'No run to describe yet',
  assumptions: 'Assumptions and limits',
  assumptionsLead: 'Conditions that travel with the number. If one fails, the result says less than it appears to.',
  provenance: 'Data sources and provenance',
  produces: 'Produces',
  parameters: 'Parameters',
  codeVersion: 'Code version',
  retrieved: 'Retrieved',
  noDescription: 'No plain-language description is available for this method.',
};

export function MethodView({ model, runId, specHash }: { model: MethodModel; runId: string | null; specHash: string | null }) {
  const c = methodCopy;
  return (
    <div className={`gt-container ${styles.page}`}>
      <section aria-labelledby="m-design">
        <h2 id="m-design" className={styles.h2}>{c.design}</h2>
        <p className={styles.muted}>{c.designLead}</p>
        <Card>
          <dl className={styles.dl}>
            {model.design.map((r) => (
              <React.Fragment key={r.label}>
                <dt>{r.label}</dt>
                <dd>{r.value}</dd>
              </React.Fragment>
            ))}
          </dl>
        </Card>
      </section>

      <section aria-labelledby="m-pipe">
        <h2 id="m-pipe" className={styles.h2}>{c.pipeline}</h2>
        {model.stages.length === 0 ? (
          <EmptyState title={c.noRunTitle} body={c.noRun} />
        ) : (
          model.stages.map((st) => (
            <div key={st.stage} className={styles.stage}>
              <h3 className={styles.h3}>{st.stage}</h3>
              {st.steps.map((s) => (
                <Card key={s.method} className={styles.step}>
                  <h4 className={styles.h4}>{s.title}</h4>
                  {s.summary.length === 0 && <p className={styles.muted}>{c.noDescription}</p>}
                  {s.summary.map((p) => (
                    <p key={p}>{p}</p>
                  ))}
                  <Lens show="explorer">
                    {s.formula.length > 0 && <pre className={styles.pre}>{s.formula.join('\n')}</pre>}
                    <p className={styles.muted}>
                      {c.produces}: {s.produces.join('; ')}
                    </p>
                  </Lens>
                  <Lens show="auditor">
                    <p className={styles.muted}>
                      <code>{s.method}</code>
                      {s.codeVersion ? ` · ${c.codeVersion} ${s.codeVersion}` : ''}
                    </p>
                    {s.parameters && (
                      <>
                        <p className={styles.muted}>{c.parameters}</p>
                        <pre className={styles.pre}>{s.parameters}</pre>
                      </>
                    )}
                  </Lens>
                </Card>
              ))}
            </div>
          ))
        )}
      </section>

      {model.assumptions.length > 0 && (
        <section aria-labelledby="m-assume">
          <h2 id="m-assume" className={styles.h2}>{c.assumptions}</h2>
          <p className={styles.muted}>{c.assumptionsLead}</p>
          <Card tone="sunken">
            <ul className={styles.list}>
              {model.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </Card>
        </section>
      )}

      {(model.sources.length > 0 || runId) && (
        <section aria-labelledby="m-prov">
          <h2 id="m-prov" className={styles.h2}>{c.provenance}</h2>
          <Card>
            <dl className={styles.dl}>
              {model.sources.map((s) => (
                <React.Fragment key={`${s.source}${s.uri}`}>
                  <dt>{s.source}</dt>
                  <dd>
                    {s.uri ?? 'No identifier recorded'}
                    {s.retrievedAt ? ` · ${c.retrieved} ${s.retrievedAt}` : ''}
                  </dd>
                </React.Fragment>
              ))}
              <Lens show="auditor">
                {runId && (
                  <>
                    <dt>Run id</dt>
                    <dd>{runId}</dd>
                  </>
                )}
                {specHash && (
                  <>
                    <dt>Specification hash</dt>
                    <dd>{specHash}</dd>
                  </>
                )}
              </Lens>
            </dl>
          </Card>
        </section>
      )}
    </div>
  );
}
