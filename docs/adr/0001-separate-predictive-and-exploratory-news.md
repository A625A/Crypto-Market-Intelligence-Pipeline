# Separate predictive and exploratory news by availability

Daily predictive rows use only information substantiated as available by the
end of UTC day t to predict close[t+1] / close[t] - 1. Publication time alone is
insufficient: articles accessible only after the cutoff cannot enter that
row, even when they describe events from day t. We retain delayed historical
articles for a separate exploratory view, including publication-day sentiment
comparisons and theme analysis, rather than expanding predictive history by
assuming past availability. This sacrifices usable historical training data
to preserve the meaning of the predictive experiment.

News has a stricter source-specific cutoff of 23:00 UTC on day t. This does
not change the overall end-of-day market target. A collection's scheduled
start time is not evidence that its results were available at that time:
records saved after 23:00 are ineligible for that day's predictive news row.

For predictive news, eligibility starts at the first successful retrieval and
preservation of that article version. Do not infer eligibility by adding 24
hours to publication time. Preserve timestamped snapshots and revisions;
later text must never replace the version used in a past forecast. Delayed
articles may enter subsequent predictive rows once retrieved, while their
publication-day associations remain available for exploratory analysis.

Audit the existing market, macroeconomic, and Fear & Greed baseline against
the same cutoff requirement. State unresolved historical availability
assumptions explicitly rather than describing the combined experiment as
proven leakage-safe. Collection is intended once per 24 hours, initially
scheduled at configurable 23:00 UTC. Consequently, a run started at that time
will ordinarily deliver records after that day's news cutoff. A successful
collection means a successful scan of configured queries, not exhaustive
coverage of all relevant articles. Failed or unsuccessful collections leave
the affected coverage incomplete.
