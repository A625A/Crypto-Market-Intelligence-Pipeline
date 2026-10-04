# 01: NewsAPI Cleanup and Daily Feature Engineering

**What to build:** Transform saved raw NewsAPI responses into reproducible
cleaned article-level data and daily news features for BTC, ETH, and SOL.
Deliver activity and financial-tone features together, in separate columns,
with evidence of availability and collection coverage so the output can later
be evaluated without backdating news.

**Blocked by:** None (can start immediately using representative raw fixtures
with explicit retrieval and coverage metadata).

**Status:** resolved

## Scope

Raw NewsAPI data → cleaned article-level data → daily asset-level news features.
Implement a runnable, documented transformation with focused automated tests.
Follow the domain glossary and the ADR separating predictive and exploratory
news. This ticket produces feature tables; it makes no claim of predictive lift.

## Acceptance criteria

### Inputs and cleaned articles

- [x] Accept saved NewsAPI payloads with explicit UTC retrieval/persistence
  timestamps and collection metadata identifying run, query, covered interval,
  and successful, incomplete, or failed scanning. Document the input contract.
  Fixtures may supply this metadata; implementing a live collector is not required.
- [x] Preserve article identity, source, URL, title, optional description,
  publication timestamp, first successful retrieval, observed version, and
  asset associations. Retain raw inputs and rejection reasons for malformed
  or unusable records. Do not modify historical raw data to repair provenance.
- [x] Require direct asset relevance rather than trusting the query bucket.
  Document deterministic v1 relevance rules and cover ambiguous ticker matches,
  especially SOL. Preserve all legitimate BTC, ETH, and SOL associations.
- [x] Remove repeated copies of the same article version and make reruns
  idempotent. Preserve legitimate articles from different publishers, even
  when they repeat an event. Preserve revisions without replacing earlier
  text or recounting a revision as a newly discovered article.
- [x] Raw snapshots lacking trustworthy retrieval evidence remain usable for
  explicitly exploratory cleaning only. Do not infer availability from file
  modification time, publication time plus 24 hours, or the scheduled run time.
  Missing coverage evidence cannot produce a successful predictive coverage flag.

### Daily eligibility and coverage

- [x] Produce one row per requested UTC date and asset, with unique date/asset
  keys and no dependence on joining market prices. Preserve requested rows
  when news is absent, incomplete, or unavailable.
- [x] Use a configurable predictive news cutoff, default 23:00 UTC. For day t,
  count articles first retrieved and saved after the previous day's cutoff
  and at or before day t's cutoff. The approved window convention is: a record saved at 23:00:01 on day t first belongs to day
  t+1's window, not day t's row. A request starting before cutoff but completing
  after it does not qualify merely because it started earlier.
- [x] Select only article versions preserved by that cutoff. Later retrievals,
  revisions, and story matches must not change past feature rows when source
  history and the transformation configuration are unchanged. Never overwrite
  an earlier article version with later text during historical feature builds.
- [x] Use collection metadata to distinguish a successful configured-query
  scan with zero new relevant articles from an incomplete, failed, or missed
  collection. A successful scan is not a guarantee of internet-wide coverage.
  Incomplete coverage leaves affected news aggregates null with an explicit
  coverage flag; zero counts are reserved for confirmed zero-article windows.

### Activity and financial tone

- [x] Include article count, unique source count,
  `estimated_distinct_story_count`, and a repeated-coverage measure. Estimate
  story groups using conservative headline similarity, asset relevance, and
  publication proximity; record rule versions and inspectable assignments.
  Use only information eligible at the row's cutoff. Advanced clustering is
  not required.
- [x] Include daily mean article age and mean time since first retrieval,
  with explicit units, measured at the predictive news cutoff. Publication
  time controls news age; retrieval controls eligibility. Repeated unchanged
  fetches do not reset either article age or first retrieval.
- [x] Score titles and descriptions separately with a fixed local FinBERT
  checkpoint. Pin the exact model and tokenizer revisions and record relevant
  preprocessing and scoring versions. Retain positive, neutral, and negative
  financial-tone scores at article level. These are text-tone scores, not
  price-direction probabilities or asset-specific sentiment.
- [x] Aggregate title and description scores into separate daily mean columns,
  with the number of scored texts for each. An absent description stays null
  and is excluded from its sentiment denominator. Empty windows have zero
  activity counts and null age/sentiment aggregates. Scoring failure must not
  silently become neutral sentiment or successful sentiment coverage.
- [x] Keep activity and sentiment columns separable for later ablations. Do
  not add news decay, rolling-history experiments, or training recency weights.

### Verification and handoff

- [x] Demonstrate the full raw-to-clean-to-daily flow using small local fixtures
  for all three assets, including duplicate and multi-asset articles, missing
  descriptions, revisions, delayed retrieval, and incomplete collection.
- [x] Test exact cutoff boundaries, publication-versus-retrieval assignment,
  unknown provenance, repeated-fetch idempotency, no-news versus missing-news
  semantics, aggregate denominators, and stable past rows after future data
  is appended. Test missing coverage independently from missing retrieval time.
- [x] Keep routine tests deterministic and independent of live NewsAPI calls
  or model downloads. Separately smoke-test the pinned scorer and document
  a small manual review of title/description tone on crypto examples without
  claiming a validated sentiment accuracy or predictive improvement.
- [x] Document the input/output schemas, aggregation and relevance rules,
  model setup, command to run the transformation, and provenance limitations.
  Verify the existing relevant tests continue to pass.

## Outside this ticket

API extraction changes, pagination and retry policies, snapshot collection,
scheduling or deployment; Fear & Greed or market-data joins; baseline audits;
model training, tuning, calibration, walk-forward evaluation, backtesting,
decay experiments; full-article scraping, asset-specific sentiment, and advanced
story clustering. Predictive production use still requires an upstream producer
of the declared provenance and coverage metadata, but that does not block
building and verifying this transformation against fixtures.


## Answer

Resolved on 2026-10-04. The standalone raw-to-clean-to-daily transformation
is implemented and documented, including article/version history, first
retrieval eligibility, the 23:00 UTC cutoff, conservative collection coverage,
multi-asset relevance, activity features, and separate title/description
FinBERT financial-tone features. Existing spec and ADR were reused.

### Verification evidence

The successful verification from the interrupted run applies to commit
`67911e8`; the checkout was clean at that same commit when resumed:

- Full suite: **125 passed**, including cached offline FinBERT inference.
- Type checks: passed for all three new modules.
- Standards review: zero outstanding material findings.
- Spec review: zero outstanding material implementation findings; its remaining
  manual-review documentation requirement is recorded below.
- The modeling dataset module is unchanged from the implementation base.

No source code changed during completion. Tests and model inference were not
rerun; only existing saved synthetic outputs were inspected for this handoff.

### Manual inspection of synthetic financial tone

On 2026-10-04 the assistant inspected the existing article-level demo output
against the wording of its small synthetic crypto examples:

| Text | Expected tone from wording | Saved FinBERT result | Assessment |
|---|---|---|---|
| Title: “Bitcoin Ethereum and Solana companies report strong profit growth.” | Positive | Positive 0.954620 | Matches explicit profit-growth wording. |
| Title: “Bitcoin company reports severe losses.” | Negative | Negative 0.969481 | Matches explicit loss wording. |
| Description: “Bitcoin demand declines.” | Negative | Negative 0.969067 | Matches explicit declining-demand wording. |
| Missing description on the profit-growth article | Unavailable | All three description scores null | Correctly excluded instead of treated as neutral. |

This is a small qualitative inspection of synthetic examples, not a labeled
real-news evaluation, an estimate of sentiment accuracy, or evidence of
predictive value. Ambiguous financial tone and crypto-specific phrasing remain
unvalidated; the scores describe text tone, not next-day price probabilities.

### Predictive-use boundary

The transformation is ready to produce candidate predictive features when
supplied complete snapshot history with truthful retrieval/persistence times
and run, query, asset, interval, and scan-outcome metadata. The current live
extractor still overwrites a legacy response file without that evidence.
Those snapshots remain exploratory; this ticket does not make them historically
eligible for prediction. Collection changes, snapshot preservation, scheduling,
dataset integration, and modeling remain separate work. Starting collection at
23:00 normally finishes after the cutoff, so those results cannot enter that
day's predictive row.
