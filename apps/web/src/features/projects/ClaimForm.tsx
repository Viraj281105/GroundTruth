'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds';
import {
  FORM_HELP,
  PERIOD_MAX,
  STATEMENT_MAX,
  UNIT_MAX,
  validateClaimForm,
  type ClaimFormState,
  type ClaimKindView,
  type FormCheck,
  type FormErrors,
} from './claims.model';
import styles from './claims.module.css';

export interface ClaimFormProps {
  initial: ClaimFormState;
  kinds: readonly ClaimKindView[];
  submitLabel: string;
  busy?: boolean;
  /** An error from the last attempt (from the API), shown as sent. */
  error?: string | null;
  /** Rendered above the fields, for example what the document originally said. */
  intro?: React.ReactNode;
  onSubmit: (fields: Extract<FormCheck, { ok: true }>['fields']) => void;
  onCancel: () => void;
  idPrefix?: string;
}

/** Small form used to add, correct or type a claim. Checks the entries before anything is sent. */
export function ClaimForm({ initial, kinds, submitLabel, busy = false, error = null, intro, onSubmit, onCancel, idPrefix = 'claim' }: ClaimFormProps) {
  const [form, setForm] = useState<ClaimFormState>(initial);
  const [errors, setErrors] = useState<FormErrors>({});
  const set = (k: keyof ClaimFormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const selected = kinds.find((k) => k.kind === form.kind);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const check = validateClaimForm(form, kinds);
    if (!check.ok) return setErrors(check.errors);
    setErrors({});
    onSubmit(check.fields);
  }

  const id = (n: string) => `${idPrefix}-${n}`;
  const err = (n: keyof ClaimFormState) => (errors[n] ? <span id={id(`${n}-err`)} role="alert" className={styles.fieldError}>{errors[n]}</span> : null);

  return (
    <form className={styles.form} onSubmit={submit} aria-label={submitLabel} noValidate>
      {intro}
      <label className={styles.field} htmlFor={id('statement')}>
        <span className={styles.label}>The claim, in words</span>
        <textarea id={id('statement')} rows={3} maxLength={STATEMENT_MAX + 200} value={form.statement} onChange={set('statement')} aria-invalid={!!errors.statement} aria-describedby={id('statement-help')} />
        <span id={id('statement-help')} className={styles.help}>{FORM_HELP.statement}</span>
        {err('statement')}
      </label>

      <label className={styles.field} htmlFor={id('kind')}>
        <span className={styles.label}>What kind of claim is it?</span>
        <select id={id('kind')} value={form.kind} onChange={set('kind')} aria-invalid={!!errors.kind}>
          <option value="">Choose a type…</option>
          {kinds.map((k) => (
            <option key={k.kind} value={k.kind}>
              {k.label}
            </option>
          ))}
        </select>
        {selected && (
          <span className={styles.help} data-kind-note>
            {selected.note}
            {!selected.checkable && ' The platform has no check for this type of claim, so it will be shown as not enough evidence to test.'}
          </span>
        )}
        {err('kind')}
      </label>

      <div className={styles.row}>
        <label className={styles.field} htmlFor={id('value')}>
          <span className={styles.label}>Number</span>
          <input id={id('value')} type="text" inputMode="decimal" value={form.value} onChange={set('value')} aria-invalid={!!errors.value} />
          <span className={styles.help}>{FORM_HELP.value}</span>
          {err('value')}
        </label>
        <label className={styles.field} htmlFor={id('unit')}>
          <span className={styles.label}>Unit</span>
          <input id={id('unit')} type="text" maxLength={UNIT_MAX + 20} value={form.unit} onChange={set('unit')} aria-invalid={!!errors.unit} />
          <span className={styles.help}>{FORM_HELP.unit}</span>
          {err('unit')}
        </label>
        <label className={styles.field} htmlFor={id('period')}>
          <span className={styles.label}>Period</span>
          <input id={id('period')} type="text" maxLength={PERIOD_MAX + 20} value={form.period} onChange={set('period')} aria-invalid={!!errors.period} />
          <span className={styles.help}>{FORM_HELP.period}</span>
          {err('period')}
        </label>
      </div>

      {error && (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      )}
      <div className={styles.actions}>
        <Button type="submit" loading={busy}>
          {submitLabel}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
