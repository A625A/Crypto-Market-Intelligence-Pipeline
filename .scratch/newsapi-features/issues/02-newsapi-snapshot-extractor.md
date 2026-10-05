# 02: Real NewsAPI Snapshot Extractor

**Status:** resolved

**Blocked by:** 01 (resolved)

## Scope and approved decisions

Collect live-style NewsAPI responses into the existing collections contract,
with one immutable file per asset scan in a unique run directory. Preserve
combined articles once plus compact page/attempt evidence. Search titles and
descriptions using full asset names or context-qualified tickers, with a
configurable three-day publication lookback. Keep publication bounds separate
from consecutive 23:00 UTC availability windows.

Limit each asset to ten requests including retries. Retry connection failures,
timeouts and server errors twice, after two and five seconds, within that
allowance. Stop all requests on shared authentication, rate-limit or quota
failure; otherwise save the asset outcome and continue. Provider result limits
produce incomplete scans without automatic interval splitting.

## Acceptance criteria

- [x] Preserve per-asset snapshots without overwriting earlier runs, and record
  actual durable payload preservation in aware UTC retrieval timestamps.
- [x] Emit run/query/window/status metadata compatible with the existing cleaner.
- [x] Audit pagination, counts, retries and stopping reasons without credentials;
  incomplete scans cannot masquerade as successful empty scans.
- [x] Respect per-asset request limits, bounded transient retries and global stops.
- [x] Verify single/multiple pages, failed/partial scans, inconsistent totals,
  cutoff crossings, immutable storage and the three-asset downstream flow with
  fake HTTP, controlled clocks and deterministic sentiment.
- [x] Run focused and full tests, review Standards and Spec, fix material findings
  and reverify; document invocation, output contract and limitations.

## Boundaries

No downstream behavior changes, modeling, scheduler installation, new dependencies,
live quota use without separate approval, commits or pushes. Existing legacy
snapshots remain exploratory. The collector does not prove predictive value.

## Comments

The user approved implementation after selecting all ten collector decisions.
The existing 30-second request timeout and 23:00 UTC scheduling convention remain.
Publication bounds are fixed at run start. A scan saved after a cutoff belongs
to the next eligible availability window. Earlier failed scans remain evidence;
a later successful rerun does not erase them from downstream coverage checks.


## Answer

Completed on 2026-10-04 (user local date). Implemented the approved collector,
command-line entry point, snapshot/audit contract and documentation. No downstream
source files changed; no new dependencies, commits or pushes.

### Verification

- 35 extractor tests cover pagination, response anomalies, retry budgets,
  global stops, asset isolation, snapshot immutability, exact cutoff inclusion,
  persistence failures and downstream integration.
- Final full suite: **160 passed**, including cached offline FinBERT inference.
- Extractor mypy check passed; diff whitespace checks passed.
- Direct-script help works from outside the repository without API calls.
- Independent Standards review: zero material findings.
- Independent Spec review: zero material findings.
- Corrected README wording about private checkpoint cleanup on write failure.
  Added cutoff-boundary and disk-failure checks and reran the full suite afterward.

### User-approved live smoke check

Explicit permission was granted for at most three requests, one per asset and
no retries. Exactly **3 requests** were used. The run was recorded at approximately
2026-10-05 04:09 UTC (2026-10-04 in the user's local timezone).

Run ID: `20261005T040903802748Z-2b6a525c3f6449b4b31ff48bc0a7dcd1`.

| Asset | API total / downloaded | Collector status | Daily relevant article count | Coverage |
|---|---:|---|---:|---|
| BTCUSDT | 97 / 97 | success | 89 | complete |
| ETHUSDT | 35 / 35 | success | 31 | complete |
| SOLUSDT | 38 / 38 | success | 37 | complete |

The saved snapshots were passed through the unchanged cleaner and daily builder
with cached local FinBERT. Cleaning rejected **0** records and retained **157**
article/asset versions after relevance and duplicate handling. All title and
description rows in this particular sample were scored. Multi-asset associations
mean these counts are not necessarily counts of distinct global articles.

Ignored local artifacts:

- Raw: `data/raw/newsapi/<run-id>/*USDT.json`.
- Cleaned: `data/processed/newsapi-collector-smoke/<run-id>/`.
- Features and `smoke-audit.json`:
  `data/processed/features/newsapi-collector-smoke/<run-id>/`.

The three outcomes belong to `(2026-10-04 23:00 UTC, 2026-10-05 23:00 UTC]`.
The generated October 5 rows are smoke-build previews for that cutoff, not
completed end-of-day forecasts. This establishes real-response compatibility,
not validated sentiment accuracy, exhaustive news coverage or predictive lift.

### Handoff limits

The collector is manually executable; no scheduler is installed. Per-run budgets
do not account for other uses of the API key. Publication search results can
change while paging; count/duplicate checks do not create a frozen provider
index. Failed scan evidence is retained, so a successful rerun may not restore
that window's downstream coverage. Completed snapshots survive later asset
failures; the current unpublished scan may be lost on interruption or disk error.
Use all completed snapshot files when reconstructing first retrieval history.
