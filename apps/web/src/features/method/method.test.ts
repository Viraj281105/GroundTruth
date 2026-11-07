import { describe, expect, it } from 'vitest';
import { GLOSSARY_TERMS, glossary } from '../../lib/glossary';
import { METHOD_COPY } from './copy';
import { CLAIMS_COPY } from '../claims/copy';

const BANNED = /\bfraud\w*|\bscam\b|\billegal\w*|\bcriminal\b|\bguilty\b|\bdefinitiv\w*|\bproves? that\b|\bcertainly\b/i;

describe('neutral wording', () => {
  it('method and claims copy avoid prohibited wording', () => {
    expect(JSON.stringify(METHOD_COPY)).not.toMatch(BANNED);
    expect(JSON.stringify(CLAIMS_COPY)).not.toMatch(BANNED);
  });
  it('states that the AI never computes', () => {
    expect(METHOD_COPY.ai.doesNot.join(' ')).toMatch(/never computes/);
  });
  it('every glossary term resolves to an entry usable as an anchor', () => {
    expect(GLOSSARY_TERMS.length).toBeGreaterThan(0);
    for (const id of GLOSSARY_TERMS) {
      expect(glossary(id)).not.toBeNull();
      expect(id).toMatch(/^[a-z0-9-]+$/);
    }
  });
});
