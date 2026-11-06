'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';
import { resolveCommands, type PaletteCase, type PaletteItem } from '../../lib/palette-core';
import styles from './CommandPalette.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
  cases: PaletteCase[];
  recent: string[];
  onAction: (action: string) => void;
}

/** Ctrl/⌘+K palette: jump anywhere, run actions, or type "compare kariba and mikoko". */
export function CommandPalette({ open, onClose, cases, recent, onAction }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const items = useMemo(() => resolveCommands(query, { cases, recent }), [query, cases, recent]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
      setQuery('');
      setIndex(0);
      inputRef.current?.focus();
    }
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => setIndex(0), [query]);

  const run = (item: PaletteItem) => {
    onClose();
    if (item.href) router.push(item.href);
    else if (item.action) onAction(item.action);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setIndex((i) => Math.min(i + 1, Math.max(items.length - 1, 0)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && items[index]) {
      e.preventDefault();
      run(items[index]);
    }
  };

  let lastGroup = '';
  return (
    <dialog ref={dialogRef} className={styles.dialog} aria-label="Command palette" onClose={onClose} onClick={(e) => e.target === dialogRef.current && onClose()}>
      <div className={styles.box} onKeyDown={onKeyDown}>
        <div className={styles.field}>
          <Search size={18} aria-hidden="true" />
          <input
            ref={inputRef}
            className={styles.input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search cases, pages and actions, or try “compare kariba and mikoko”"
            aria-label="Command"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={items[index] ? `palette-${items[index].id}` : undefined}
          />
          <kbd>Esc</kbd>
        </div>
        <ul id="palette-list" className={styles.list} role="listbox">
          {items.length === 0 && <li className={styles.empty}>Nothing matches “{query}”.</li>}
          {items.map((item, i) => {
            const header = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <React.Fragment key={item.id}>
                {header && (
                  <li className={styles.group} role="presentation">
                    {header}
                  </li>
                )}
                <li id={`palette-${item.id}`} role="option" aria-selected={i === index} className={`${styles.item} ${i === index ? styles.on : ''}`} onMouseMove={() => setIndex(i)} onClick={() => run(item)}>
                  <span>{item.label}</span>
                  {item.hint && <span className={styles.hint}>{item.hint}</span>}
                </li>
              </React.Fragment>
            );
          })}
        </ul>
      </div>
    </dialog>
  );
}
