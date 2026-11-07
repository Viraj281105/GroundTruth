import { describe, expect, it } from 'vitest';
import { buildFacts, faqs, featureList, flowSteps } from '../src/features/home/data';

describe('home data', () => {
  it('builds facts, hiding the case count when unknown', () => {
    expect(buildFacts(3)[0]).toMatchObject({ id: 'cases', value: 3 });
    expect(buildFacts(1)[0].label).toBe('benchmark case');
    expect(buildFacts(null).some((f) => f.id === 'cases')).toBe(false);
    expect(buildFacts(null).find((f) => f.id === 'real')?.value).toBe(0);
  });
  it('has the expected section content and no fraud claims', () => {
    expect(featureList).toHaveLength(6);
    expect(flowSteps).toHaveLength(6);
    expect(faqs).toHaveLength(5);
    expect(JSON.stringify(faqs)).not.toMatch(/proves? fraud|is fraudulent/i);
  });
});
