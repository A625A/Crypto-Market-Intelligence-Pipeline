"""Opt-in real-model check; ordinary tests never download model weights."""
import os
import pytest

pytestmark = pytest.mark.skipif(os.getenv('RUN_FINBERT_SMOKE') != '1',
                               reason='set RUN_FINBERT_SMOKE=1 for the pinned local model')


def test_pinned_finbert_scores_financial_tone_locally():
    from src.features.news_sentiment import FinBertScorer
    scorer = FinBertScorer()
    result = scorer.score(['Bitcoin company reports strong profit growth.',
                           'Ethereum company reports severe losses and bankruptcy.'])
    assert len(result) == 2
    assert result[0]['positive'] > result[0]['negative']
    assert result[1]['negative'] > result[1]['positive']
    for item in result:
        assert set(item) == {'positive', 'negative', 'neutral'}
        assert sum(item.values()) == pytest.approx(1.0, abs=1e-6)
    assert scorer.metadata['revision'] == '4556d13015211d73dccd3fdd39d39232506f3e43'
