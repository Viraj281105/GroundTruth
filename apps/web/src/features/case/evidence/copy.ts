/** English copy for the evidence, playground, map and robustness views. Neutral wording only (R2). */
export const COPY = {
  errorTitle: 'The analysis could not be loaded',
  noRunTitle: 'No stored analysis for this case yet',
  noRunBody:
    'Nothing has been measured for this case in this session, so there is nothing to show. Run an analysis to see the counterfactual and its checks.',
  noRunAction: 'Open the run page',

  evidenceTitle: 'Evidence',
  evidenceLead:
    'How the comparison was built and how well it holds up. Each section answers one question.',
  sections: {
    chart: {
      title: 'What did the land look like against its counterfactual?',
      lead: 'The observed series next to the counterfactual estimated from comparable untreated areas. The gap after the intervention is the estimated difference, with its uncertainty.',
    },
    fit: {
      title: 'Did the comparison track the project area before the intervention?',
      lead: 'A counterfactual is only worth reading if it followed the project area closely beforehand.',
    },
    placebo: {
      title: 'Does the result stand out from chance?',
      lead: 'The same method applied to areas that were never part of the project gives a reference spread.',
    },
    donors: {
      title: 'Which areas make up the comparison?',
      lead: 'The pool of untreated areas, the ones kept and the ones set aside, and where the project boundary lies.',
    },
    playground: {
      title: 'Try a different assumption',
      lead: 'Move the intervention year or switch donors off. Only results the engine already produced are shown; anything else needs a new run.',
    },
  },
  chartMissing:
    'The counterfactual path is not served by the API yet, so the chart cannot be drawn for this run. The numeric evidence below is complete.',
  placeboMissing:
    'The placebo distribution is not served by the API yet. The p-value and counts below come from the evidence bundle.',
  demoNote: 'These values come from the bundled simulated fixture, not a measured run.',
} as const;
