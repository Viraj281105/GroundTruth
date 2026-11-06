/** English copy for "How it works". Neutral wording (R2): no accusation, no certainty. */
export const METHOD_COPY = {
  title: 'How it works',
  intro: 'GroundTruth estimates what would likely have happened to a piece of land without a project, then sets that estimate beside what the project reports. This page explains each step, what the AI does and does not do, and where the method stops being reliable.',
  steps: {
    title: 'The method in three steps',
    items: [
      {
        heading: '1. Build a comparison',
        body: 'Satellite records of the project area before the project began are matched against many similar areas that were not part of it. A weighted blend of those areas, a synthetic control, is chosen so that it follows the project area closely over the years before the project.',
      },
      {
        heading: '2. Estimate the difference',
        body: 'After the project start, the blend continues as the estimate of what would likely have happened without the project, the counterfactual. The gap between what satellites observed and that estimate is the estimated effect, reported with its uncertainty.',
      },
      {
        heading: '3. Stress-test the result',
        body: 'The same procedure is repeated on areas that had no project (placebo tests), on earlier dates, with each comparison area left out in turn, and under alternative settings. A result that does not stand out from these checks is reported as inconclusive, not stretched.',
      },
    ],
  },
  ai: {
    title: 'What the AI does and does not do',
    does: [
      'Writes plain-language narration of numbers the engine has already computed.',
      'Every number in that narration is checked against the evidence; text with an unmatched number is rejected and replaced by a fixed template.',
    ],
    doesNot: [
      'It never computes an estimate, a weight, a p-value or a verdict.',
      'It is not used to decide which areas are comparable.',
      'It cannot change a result; it can only describe one.',
    ],
    status: 'AI narration is not switched on in this build. Reports use fixed templates.',
  },
  assumptions: {
    title: 'Assumptions',
    items: [
      'Comparison areas were not themselves affected by the project (no spill-over).',
      'The blend that tracks the project area before the project would have kept tracking it afterwards.',
      'Satellite measures such as a vegetation index are consistent over time and across sensors.',
      'The set of comparison areas covers the conditions the project area faced.',
    ],
  },
  limits: {
    title: 'Limits and honest status',
    items: [
      'Analyses currently run on simulated data and are labelled as simulated wherever they appear.',
      'Retrieval of real satellite data is not implemented yet; such requests are refused rather than filled in.',
      'A vegetation index is not carbon. Conversion to tonnes of CO2 is not implemented, because it needs site-specific allometry and an error budget.',
      'A result depends on its comparison areas. A thin or poorly matched set weakens it, and the engine says so.',
      'A divergence between the estimate and a project claim warrants accredited review. It is a screening signal, not a finding about any person or organisation.',
    ],
  },
  glossary: {
    title: 'Glossary',
    intro: 'Every term the interface explains, in plain language first and technical wording second.',
    plain: 'In plain words',
    technical: 'Technically',
  },
} as const;
