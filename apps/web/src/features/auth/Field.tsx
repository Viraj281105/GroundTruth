'use client';

import React, { useId, useState } from 'react';
import styles from './auth.module.css';

interface FieldProps {
  label: string;
  type?: 'text' | 'email' | 'password';
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
  error?: string | null;
  hint?: string;
  describedBy?: string;
  required?: boolean;
  autoFocus?: boolean;
}

/** A labelled input. Errors are tied by aria-describedby; passwords get a show/hide toggle. */
export function Field({ label, type = 'text', value, onChange, autoComplete, error, hint, describedBy, required = true, autoFocus }: FieldProps) {
  const id = useId();
  const [shown, setShown] = useState(false);
  const errId = `${id}-err`;
  const hintId = `${id}-hint`;
  const ids = [error ? errId : '', hint ? hintId : '', describedBy ?? ''].filter(Boolean).join(' ') || undefined;
  const isPassword = type === 'password';
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <div className={isPassword ? styles.inputWrap : undefined}>
        <input
          id={id}
          className={`${styles.input} ${error ? styles.invalid : ''}`}
          type={isPassword && shown ? 'text' : type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={ids}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          autoFocus={autoFocus}
        />
        {isPassword && (
          <button type="button" className={styles.toggle} onClick={() => setShown((s) => !s)} aria-pressed={shown} aria-label={`${shown ? 'Hide' : 'Show'} ${label.toLowerCase()}`}>
            {shown ? 'Hide' : 'Show'}
          </button>
        )}
      </div>
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
      {error && (
        <p id={errId} className={styles.fieldError} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className={styles.error} role="alert">
      {message}
    </p>
  );
}
