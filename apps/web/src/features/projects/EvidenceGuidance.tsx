import React from 'react';
import { Card, Chip, LinkButton } from '../../components/ds';
import type { Schemas } from '../../lib/api-client';
import styles from './documents.module.css';

type Inventory = Schemas['EvidenceInventoryView'];

/** What is missing and what the user can do next, exactly as the API states it. Renders nothing it was not given. */
export function EvidenceGuidance({
  inventory,
  observationHref,
}: {
  inventory: Pick<Inventory, 'missing_evidence' | 'next_steps' | 'observation_ingestion'>;
  /** The project's Earth Observation tab. When given and ingestion is available, the card links there. */
  observationHref?: string;
}) {
  const missing = inventory.missing_evidence ?? [];
  const steps = inventory.next_steps ?? [];
  const ing = inventory.observation_ingestion;
  if (missing.length === 0 && steps.length === 0 && !ing) return null;
  return (
    <Card aria-label="What is missing and what to do next" className={styles.guidance}>
      <h2 className={styles.h2}>What is missing and what to do next</h2>
      {ing && (
        <p className={styles.ingestion} data-ingestion-available={ing.available}>
          <Chip tone={ing.available ? 'accent' : 'caution'}>{ing.available ? 'Satellite data can be added' : 'Satellite data cannot be added here'}</Chip> {ing.message}
          {ing.available && observationHref && (
            <LinkButton href={observationHref} variant="secondary" size="sm">
              Request satellite data
            </LinkButton>
          )}
        </p>
      )}
      {missing.length > 0 && (
        <div>
          <h3 className={styles.h3}>Still missing</h3>
          <ul className={styles.list}>
            {missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {steps.length > 0 && (
        <div>
          <h3 className={styles.h3}>What you can do next</h3>
          <ul className={styles.list}>
            {steps.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
