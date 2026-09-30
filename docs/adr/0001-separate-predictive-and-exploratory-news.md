# Separate predictive and exploratory news by availability

Daily predictive rows use only information substantiated as available by the
end of UTC day t to predict close[t+1] / close[t] - 1. Publication time alone is
insufficient: articles accessible only after the cutoff cannot enter that
row, even when they describe events from day t. We retain delayed historical
articles for a separate exploratory view, including publication-day sentiment
comparisons and theme analysis, rather than expanding predictive history by
assuming past availability. This sacrifices usable historical training data
to preserve the meaning of the predictive experiment; timestamped snapshots
will preserve evidence for future evaluations. The precise availability
evidence and collection policy remain to be decided.
