# NewsAPI daily features

Status: cleanup, daily features and the real snapshot collector are implemented; wider research remains out of scope.

## Purpose

Andrew will use this pipeline to investigate whether news adds predictive
information beyond market, macroeconomic, and Fear & Greed features for BTC,
ETH, and SOL.

## Settled decisions

- Preserve the existing daily target: the row for UTC day t predicts the
  same asset's close-to-close return for day t+1.
- Preserve binary direction labels: 1 is a strictly positive return (up),
  and 0 is a zero or negative return (non-up). Label probability outputs as
  probability of up and probability of non-up. Expected return is separate.
- Information must have been available by the end of UTC day t.
- News has a stricter cutoff of 23:00 UTC on day t, while the market target
  remains end-of-day close to next-day close. Never substitute the scheduled
  run start time for the timestamp of successful retrieval and preservation.
- Use the first successful retrieval and preservation of each article version
  as conservative evidence of availability. Never infer historical eligibility
  as publication time plus 24 hours, or replace past text with later revisions.
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
- Distinguish completed collection with no relevant articles from incomplete
  or failed collection. Preserve the market row, flag news coverage, and leave
  affected news aggregates missing for incomplete or failed collection.
- Begin with news directly relevant to BTC, ETH, or SOL. Broader industry news
  is outside the initial scope.
- Remove exact duplicates while preserving legitimate articles from different
  publishers. Distinguish article volume from distinct-story volume and track
  repeated coverage of the same event separately.
- Allow an article to be associated with multiple assets when relevant to each.
- Daily news activity counts newly retrieved and saved articles, not unchanged
  articles returned again by later requests. Preserve revisions separately.
- Audit availability assumptions in the existing non-news baseline alongside
  news, and make unresolved historical assumptions explicit.

## Initial features

Build news activity and sentiment in the first implementation, with separate
columns so activity-only, sentiment-only, and combined feature additions can
be compared against the baseline later.

- Article count.
- Unique source count.
- `estimated_distinct_story_count` and repeated-coverage measures.
- Article age based on publication time.
- Title sentiment.
- Description sentiment.
- Preserve `time_since_first_retrieval` as a separate candidate feature.

Use a fixed, pinned FinBERT version for positive, neutral, and negative
financial tone. Score titles and descriptions independently; missing
descriptions remain missing. Text-level tone shared across legitimately
associated assets is acceptable for v1; asset-specific sentiment is deferred.

Remove exact duplicates and estimate repeated stories conservatively using
headline similarity, asset relevance, and publication-time proximity. Advanced
story grouping is a later improvement, not a dependency of the first version.
Grouping must not use future articles to change past feature rows.

## Collection

- Target one scheduled collection every 24 hours.
- Use configurable 23:00 UTC as the initial collection time and document
  23:00 UTC as the predictive news cutoff.
- Record exact retrieval timestamps; scheduling itself is not proof of receipt.
- Mark failed or missed scheduled periods incomplete, never as zero-news days.
- A successful scan means the configured NewsAPI queries were scanned, not
  that all relevant articles on the internet were captured.
- Results saved after 23:00 are ineligible for that day's news row. Starting
  collection at 23:00 will ordinarily yield results after the cutoff.

## Focused implementation scope requested

Create one implementation ticket for raw NewsAPI data to cleaned article-level
data to daily asset-level news features. Scheduling, API collection changes,
baseline auditing, combined-dataset integration, model training, evaluation,
and advanced story grouping remain outside this ticket.

Use consecutive 23:00-to-23:00 news windows, assigning late retrievals to
the next eligible cutoff, as recorded in the approved implementation ticket. The transformer requires explicit collection
provenance and coverage inputs; it must not invent them for legacy snapshots.

## Historical information and recency

- Preserve historical data for training, backtesting, reproducibility, and
  feature construction. Reduced predictive weight does not imply deletion.
- Test recency-based news features and exponential decay as candidate feature
  variants in later experiments; adoption and decay strength are not settled.
- Measure news age from publication time, not first retrieval. An article
  published Monday and first retrieved Thursday is three days old on Thursday;
  retrieval still controls predictive eligibility.
- Represent older market prices mainly through rolling returns, moving
  averages, trends, and volatility rather than unlimited raw price history.
- Separately compare ordinary model training against recency-weighted training
  in a later experiment, outside the first implementation.
- Select decay and weighting approaches using walk-forward validation and
  retain them only if they improve unseen performance. Selection must not use
  the observations subsequently presented as untouched evaluation data.

## Open decisions

- Detailed relevance rules, language, exact-duplicate identity, and simple
  story-grouping thresholds to document during implementation.
- Collector interval coverage and request-budget management are settled in ticket 02 below.
- Later rolling lookbacks and candidate decay strengths.
- Evaluation metrics, walk-forward windows,
  tuning protocol, and the evidence required to claim improvement.
- Resolution of availability gaps discovered in the baseline audit.

## Related documents

- Glossary: `../../CONTEXT.md`.
- Availability decision: `../../docs/adr/0001-separate-predictive-and-exploratory-news.md`.

## Implementation interfaces

The authorized raw-to-clean interface belongs in the existing transformers
package; the clean-to-daily interface belongs in the existing features package.
Tests exercise those public interfaces with recorded collection fixtures. A
small injected sentiment-scoring interface permits the real local FinBERT
adapter and deterministic external-model test adapters. File commands wrap
these interfaces, use repository-root defaults, and produce Parquet artifacts.
The pre-implementation review base is b7180877d1b52015cca5c750d7df74266854a5dc.

## Real snapshot collector (ticket 02, implemented)

The follow-up collector implements the existing collections contract without
changing cleaner, feature, or modeling behavior. Approved decisions:

- Save an immutable JSON per asset scan, grouped under a unique UTC run ID with
  a random suffix. Repeated executions never reuse an existing run directory.
- Search the previous three publication days by default, configurable. Fix
  `from` and `to` at run start across assets, pages and retries. These bounds
  describe the publication search, not recorded availability or daily coverage.
- Search English titles and descriptions. Match a full asset name or a ticker
  qualified by crypto, cryptocurrency, blockchain, bitcoin, ethereum or solana.
  Preserve the executed query and query version; the cleaner decides relevance.
- Allow at most ten HTTP requests per asset, including retries; a lower budget
  is configurable. Retain the existing 30-second timeout. Disable redirects so
  they cannot generate unrecorded HTTP attempts.
- Retry connection failures, timeouts and HTTP 5xx up to twice per page, waiting
  two and five seconds, within the same request allowance.
- Shared authentication errors, rate limiting and quota exhaustion stop all
  requests. Save explicit skipped outcomes for assets not attempted. Other
  asset failures do not prevent subsequent assets from being attempted.
- Store combined article data once and compact attempt logs: page, attempt,
  request/response timestamps, HTTP status, reported total, article count and
  sanitized error details. Do not retain credentials or duplicate page bodies.
- Require consistent nonnegative integer result totals and distinct article
  URLs before claiming pagination completed. Invalid pages, changed totals,
  duplicate results, count mismatches, early empty pages, provider limits and
  exhausted request allowances cannot become successful empty scans. Preserve
  downloaded article evidence. Do not split publication intervals automatically.
- Record `retrieved_at` after a private payload checkpoint has been flushed and
  synced to disk. Then publish the complete envelope atomically without replacing
  a previous asset file. The timestamp represents payload preservation, not
  final envelope publication; a later formatting/publication step does not
  backdate the payload's actual preservation. Pending files are not cleaner inputs.
- Assign each saved outcome to the first configured cutoff at or after its
  actual payload preservation, with the preceding cutoff as `window_start`.
  The default is 23:00 UTC. Keep the existing 23:00 start-time convention: a
  normal run finishing afterward contributes to the following cutoff's window.
- A scan with valid completed pagination is `success`; a partially retrieved or
  malformed scan is `incomplete`; an unsuccessful scan with no usable page or
  an asset skipped after a global stop is `failed`. Downstream validation may
  further reduce coverage when it rejects article data.

Tests use fake HTTP, controlled clocks, temporary directories and deterministic
sentiment. Live quota usage requires separate explicit approval. No scheduler,
modeling integration, commits or pushes are authorized by this implementation.
The existing feature builder retains all failed scan evidence; a later success
in the same window does not automatically repair coverage. A disk write failure
aborts the run while leaving previously published asset snapshots intact.
