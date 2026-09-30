# NewsAPI daily features

Status: design in progress; not approved for implementation.

## Purpose

Andrew will use this pipeline to investigate whether news adds predictive
information beyond market, macroeconomic, and Fear & Greed features for BTC,
ETH, and SOL.

## Settled decisions

- Preserve the existing daily target: the row for UTC day t predicts the
  same asset's close-to-close return for day t+1.
- Information must have been available by the end of UTC day t.
- Use the free NewsAPI plan and preserve timestamped snapshots going forward.
- Historical downloads are exploratory unless their availability at the
  relevant forecast cutoff can be substantiated.
- Keep publication-day exploratory analyses separate from predictive features.
  Exploratory uses include news versus Fear & Greed comparisons, recurring
  themes, and investigating possible influences without establishing causality.
- Assess direction prediction and return prediction separately. Better
  probability estimates or calibration on unseen dates can make news useful
  even if return prediction stays roughly unchanged; improvement in both is
  not required.

## Open decisions

- Availability evidence, first-observed timestamps, and article revisions.
- Collection cadence and treatment of incomplete collection versus no news.
- Article relevance, asset associations, language, and duplicate stories.
- Initial feature families and text-scoring methods.
- Exact direction classes, evaluation metrics, chronological validation,
  and the evidence required to claim improvement.
- Availability assumptions in the existing non-news baseline.

## Related documents

- Glossary: `../../CONTEXT.md`.
- Availability decision: `../../docs/adr/0001-separate-predictive-and-exploratory-news.md`.
