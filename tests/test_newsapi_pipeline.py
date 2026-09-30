import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.transformers.clean_newsapi import clean_newsapi


def article(title='Bitcoin adoption grows', url='https://example.com/a', **changes):
    result = {'title': title, 'description': 'Bitcoin payment adoption grows.',
              'url': url, 'source': {'id': None, 'name': 'Example'},
              'publishedAt': '2026-09-28T12:00:00Z'}
    result.update(changes)
    return result


def scan(articles, symbol='BTCUSDT', received='2026-09-29T22:00:00Z',
         day='2026-09-29', status='success', **changes):
    end = pd.Timestamp(day, tz='UTC') + pd.Timedelta(hours=23)
    result = {'run_id': f'{day}-{symbol}', 'symbol': symbol, 'query': symbol,
              'window_start': (end-pd.Timedelta(days=1)).isoformat(),
              'window_end': end.isoformat(), 'retrieved_at': received,
              'status': status,
              'response': {'status': 'ok', 'totalResults': len(articles), 'articles': articles}}
    result.update(changes)
    return result


def test_cleaner_deduplicates_without_erasing_multi_asset_relevance():
    item = article('Bitcoin and Ethereum adoption grows')
    result = clean_newsapi({'collections': [scan([item, item]), scan([item], symbol='ETHUSDT')]})
    assert len(result.articles) == 2
    assert set(result.articles.symbol) == {'BTCUSDT', 'ETHUSDT'}
    assert result.articles.article_id.nunique() == 1
    assert result.articles.published_at.eq(pd.Timestamp('2026-09-28T12:00:00Z')).all()
    assert result.articles.retrieved_at.eq(pd.Timestamp('2026-09-29T22:00:00Z')).all()
    assert result.rejected.empty


def test_repeated_fetch_preserves_first_retrieval_and_distinct_text_versions():
    original = article(url='https://example.com/a?utm_source=feed')
    repeated = dict(original, url='https://example.com/a#top', urlToImage='new.png')
    revised = dict(repeated, description='Ethereum also benefits from Bitcoin adoption.')
    result = clean_newsapi({'collections': [scan([original]),
        scan([repeated], received='2026-09-30T22:00:00Z', day='2026-09-30'),
        scan([revised], received='2026-10-01T22:00:00Z', day='2026-10-01')]})
    btc = result.articles.query("symbol == 'BTCUSDT'")
    eth = result.articles.query("symbol == 'ETHUSDT'")
    assert len(btc) == 2
    assert btc.article_id.nunique() == 1
    assert btc.first_retrieved_at.eq(pd.Timestamp('2026-09-29T22:00:00Z')).all()
    assert eth.first_retrieved_at.eq(pd.Timestamp('2026-10-01T22:00:00Z')).all()


def test_legacy_snapshot_cannot_invent_retrieval_or_coverage():
    result = clean_newsapi({'BTCUSDT': {'status': 'ok', 'articles': [article()]}})
    assert len(result.articles) == 1
    assert result.articles.retrieved_at.isna().all()
    assert result.articles.first_retrieved_at.isna().all()
    assert result.collections.empty


@pytest.mark.parametrize('changes', [
    {'publishedAt': 'not-a-date'}, {'publishedAt': '2026-09-28T12:00:00'},
    {'publishedAt': '2026-09-30T12:00:00Z'}, {'title': '[Removed]'}, {'url': None}])
def test_unusable_articles_are_rejected_with_reasons(changes):
    result = clean_newsapi({'collections': [scan([article(**changes)])]})
    assert result.articles.empty
    assert len(result.rejected) == 1
    assert result.rejected.iloc[0].reason
    assert result.collections.iloc[0].status == 'incomplete'


def test_ticker_relevance_requires_crypto_context_and_does_not_trust_query():
    records = [article('SOL shines in the garden', description='A sunny day.', url='https://x.test/1'),
               article('SOL blockchain sees growing adoption', description=None, url='https://x.test/2'),
               article('BTC and ETH crypto ETF demand rises', description=None, url='https://x.test/3')]
    result = clean_newsapi({'collections': [scan(records, symbol='SOLUSDT')]})
    assert set(zip(result.articles.url, result.articles.symbol)) == {
        ('https://x.test/2', 'SOLUSDT'), ('https://x.test/3', 'BTCUSDT'),
        ('https://x.test/3', 'ETHUSDT')}


def test_daily_counts_follow_first_retrieval_cutoff_not_publication():
    from src.features.news_features import build_news_features
    early = article(url='https://example.com/early')
    late = article(url='https://example.com/late')
    scans = [scan([early], received='2026-09-29T23:00:00Z'),
             scan([late], received='2026-09-29T23:00:01Z', day='2026-09-30'),
             scan([early, late], day='2026-09-30', received='2026-09-30T22:00:00Z')]
    result = build_news_features(clean_newsapi({'collections': scans}),
                                ['2026-09-29', '2026-09-30'], scorer=FixedTone())
    btc = result.daily.query("symbol == 'BTCUSDT'")
    assert btc.news_article_count.tolist() == [1, 1]
    assert btc.news_article_age_hours_mean.tolist() == pytest.approx([35, 59])
    assert len(result.daily) == 6
    assert result.daily.query("symbol == 'ETHUSDT'").news_article_count.isna().all()


@pytest.mark.parametrize('case', ['partial', 'api_error', 'unknown_retrieval', 'unknown_query', 'invalid_window'])
def test_success_claim_without_provenance_or_complete_response_is_not_zero_news(case):
    from src.features.news_features import build_news_features
    event = scan([])
    if case == 'partial': event['response']['totalResults'] = 3
    if case == 'api_error': event['response']['status'] = 'error'
    if case == 'unknown_retrieval': event.pop('retrieved_at')
    if case == 'unknown_query': event.pop('query')
    if case == 'invalid_window': event.pop('window_start')
    result = build_news_features(clean_newsapi({'collections': [event]}), ['2026-09-29'], scorer=FixedTone())
    row = result.daily.query("symbol == 'BTCUSDT'").iloc[0]
    assert not row.news_coverage_complete
    assert pd.isna(row.news_article_count)


class FixedTone:
    metadata = {'model_id': 'test-tone', 'revision': 'fixture-v1'}

    def score(self, texts):
        return [({'positive': 0.1, 'negative': 0.8, 'neutral': 0.1} if 'declines' in text
                 else {'positive': 0.7, 'negative': 0.1, 'neutral': 0.2}) for text in texts]


def test_title_description_sentiment_have_separate_denominators():
    from src.features.news_features import build_news_features
    records = [article(description='Bitcoin usage declines.'),
               article('Bitcoin adoption expands', url='https://another.test/b', description=None)]
    cleaned = clean_newsapi({'collections': [scan(records), scan([], symbol='ETHUSDT'), scan([], symbol='SOLUSDT', status='failed')]})
    result = build_news_features(cleaned, ['2026-09-29'], scorer=FixedTone())
    btc = result.daily.query("symbol == 'BTCUSDT'").iloc[0]
    assert btc.news_article_count == 2
    assert btc.news_title_scored_count == 2
    assert btc.news_description_scored_count == 1
    assert btc.news_title_positive_mean == pytest.approx(0.7)
    assert btc.news_description_negative_mean == pytest.approx(0.8)
    assert result.articles.description_negative.isna().sum() == 1
    eth = result.daily.query("symbol == 'ETHUSDT'").iloc[0]
    assert eth.news_article_count == 0
    assert pd.isna(eth.news_title_positive_mean)
    assert pd.isna(result.daily.query("symbol == 'SOLUSDT'").iloc[0].news_article_count)


@pytest.mark.parametrize('bad', [[], [{'positive': float('nan'), 'negative': 0., 'neutral': 1.}],
                                  [{'positive': 0.8, 'negative': 0.8, 'neutral': 0.8}]])
def test_invalid_sentiment_output_fails_instead_of_creating_features(bad):
    from src.features.news_features import build_news_features
    class BadTone(FixedTone):
        def score(self, texts): return bad
    with pytest.raises(ValueError, match='sentiment'):
        build_news_features(clean_newsapi({'collections': [scan([article()])]}),
                            ['2026-09-29'], scorer=BadTone())


def test_activity_keeps_publishers_but_estimates_repeated_stories():
    from src.features.news_features import build_news_features
    a = article('Bitcoin company announces major expansion', source={'name': 'Publisher A'})
    b = article('Bitcoin company announces major expansion!', url='https://other.test/b', source={'name': 'Publisher B'})
    c = article('Bitcoin network suffers prolonged outage', url='https://other.test/c', source={'name': 'Publisher B'})
    result = build_news_features(clean_newsapi({'collections': [scan([a, b, c])]}),
                                ['2026-09-29'], scorer=FixedTone())
    row = result.daily.query("symbol == 'BTCUSDT'").iloc[0]
    assert row.news_article_count == 3
    assert row.news_unique_source_count == 2
    assert row.estimated_distinct_story_count == 2
    assert row.news_repeated_coverage_count == 1
    assert row.news_time_since_first_retrieval_hours_mean == 1
    assert result.articles.story_id.nunique() == 2


def test_future_revisions_and_retrievals_cannot_change_past_features():
    from src.features.news_features import build_news_features
    original = article()
    base = [scan([original])]
    revised = article(title='Bitcoin adoption declines sharply')
    future = scan([revised, article(url='https://example.com/new')],
                  day='2026-09-30', received='2026-09-30T22:00:00Z')
    before = build_news_features(clean_newsapi({'collections': base}), ['2026-09-29'], scorer=FixedTone())
    after = build_news_features(clean_newsapi({'collections': base + [future]}), ['2026-09-29'], scorer=FixedTone())
    assert_frame_equal(before.daily, after.daily)
    assert_frame_equal(before.articles, after.articles)


def test_legacy_articles_leave_requested_predictive_rows_incomplete():
    from src.features.news_features import build_news_features
    cleaned = clean_newsapi({'BTCUSDT': {'status': 'ok', 'articles': [article()]}})
    result = build_news_features(cleaned, ['2026-09-29'], scorer=FixedTone())
    assert len(result.daily) == 3
    assert not result.daily.news_coverage_complete.any()
    assert result.daily.news_article_count.isna().all()


@pytest.mark.parametrize('dates,hour', [(['2026-09-29T12:00:00Z'],23),
                                      (['2026-09-29','2026-09-29'],23),
                                      (['2026-09-29'],24)])
def test_invalid_daily_grid_is_rejected(dates, hour):
    from src.features.news_features import build_news_features
    with pytest.raises(ValueError):
        build_news_features(clean_newsapi({'collections': []}), dates, scorer=FixedTone(), cutoff_hour=hour)


def test_file_commands_preserve_schema_and_failed_build_keeps_previous_output(tmp_path):
    import json
    from src.transformers.clean_newsapi import create_clean_newsapi
    from src.features.news_features import create_news_features
    raw = tmp_path/'raw.json'
    raw.write_text(json.dumps({'collections': [scan([article('Bitcoin Ethereum Solana adoption grows')]),
                    scan([], symbol='ETHUSDT'), scan([], symbol='SOLUSDT')]}))
    clean_dir, output_dir = tmp_path/'clean', tmp_path/'features'
    create_clean_newsapi([raw], clean_dir)
    result = create_news_features(clean_dir, output_dir, '2026-09-29', '2026-09-29', scorer=FixedTone())
    saved = pd.read_parquet(output_dir/'news_features.parquet')
    assert_frame_equal(saved, result.daily)
    assert saved.news_article_count.tolist() == [1, 1, 1]
    assert pd.read_parquet(clean_dir/'articles.parquet').published_at.dt.tz is not None
    original = (output_dir/'news_features.parquet').read_bytes()
    class FailingTone(FixedTone):
        def score(self, texts): raise RuntimeError('model unavailable')
    with pytest.raises(RuntimeError, match='model unavailable'):
        create_news_features(clean_dir, output_dir, '2026-09-29', '2026-09-29', scorer=FailingTone())
    assert (output_dir/'news_features.parquet').read_bytes() == original


def test_all_missing_days_still_have_typed_features_and_article_schema():
    from src.features.news_features import build_news_features
    result = build_news_features(clean_newsapi({'collections': []}), ['2026-09-29'], scorer=FixedTone())
    assert str(result.daily.news_article_count.dtype) == 'Int64'
    assert str(result.daily.news_title_positive_mean.dtype) == 'float64'
    assert {'article_id', 'retrieved_at', 'story_id', 'title_positive', 'date'}.issubset(result.articles.columns)


@pytest.mark.parametrize('missing_field', ['retrieved_at', 'window_start', 'window_end', 'symbol', 'query', 'run_id'])
def test_unknown_time_scan_cannot_be_hidden_by_another_successful_empty_scan(missing_field):
    from src.features.news_features import build_news_features
    incomplete = scan([article()])
    incomplete.pop(missing_field)
    events = [incomplete, scan([])]
    result = build_news_features(clean_newsapi({'collections': events}), ['2026-09-29'], scorer=FixedTone())
    row = result.daily.query("symbol == 'BTCUSDT'").iloc[0]
    assert not row.news_coverage_complete
    assert pd.isna(row.news_article_count)


@pytest.mark.parametrize('bad_articles', ['missing', None, {}])
def test_malformed_article_array_is_incomplete_not_confirmed_empty(bad_articles):
    from src.features.news_features import build_news_features
    event = scan([])
    if bad_articles == 'missing':
        event['response'].pop('articles')
    else:
        event['response']['articles'] = bad_articles
    cleaned = clean_newsapi({'collections': [event]})
    assert cleaned.collections.iloc[0].status == 'incomplete'
    result = build_news_features(cleaned, ['2026-09-29'], scorer=FixedTone())
    assert pd.isna(result.daily.query("symbol == 'BTCUSDT'").iloc[0].news_article_count)


def test_text_reversion_selects_latest_observed_version_without_recounting():
    from src.features.news_features import build_news_features
    original = article()
    revision = article(title='Bitcoin adoption declines sharply')
    events = [scan([original], received='2026-09-29T20:00:00Z'),
              scan([revision], received='2026-09-29T21:00:00Z'),
              scan([original], received='2026-09-29T22:00:00Z')]
    result = build_news_features(clean_newsapi({'collections': events}), ['2026-09-29'], scorer=FixedTone())
    row = result.daily.query("symbol == 'BTCUSDT'").iloc[0]
    assert row.news_article_count == 1
    assert row.news_title_positive_mean == pytest.approx(0.7)
    assert result.articles.iloc[0].retrieved_at == pd.Timestamp('2026-09-29T22:00:00Z')


def test_incomplete_collection_does_not_require_scoring_unusable_articles():
    from src.features.news_features import build_news_features
    class UnavailableTone(FixedTone):
        def score(self, texts): raise RuntimeError('no model available')
    result = build_news_features(clean_newsapi({'collections': [scan([article()], status='failed')]}),
                                ['2026-09-29'], scorer=UnavailableTone())
    assert not result.daily.news_coverage_complete.any()
    assert result.daily.news_title_positive_mean.isna().all()


def test_mixed_legacy_and_recorded_files_keep_exploration_separate(tmp_path):
    import json
    from src.transformers.clean_newsapi import create_clean_newsapi
    from src.features.news_features import build_news_features
    legacy, recorded = tmp_path/'legacy.json', tmp_path/'recorded.json'
    legacy.write_text(json.dumps({'BTCUSDT': {'status': 'ok', 'articles': [article()]}}))
    recorded.write_text(json.dumps({'collections': [scan([])]}))
    cleaned = create_clean_newsapi([legacy, recorded], tmp_path/'clean')
    result = build_news_features(cleaned, ['2026-09-29'], scorer=FixedTone())
    row = result.daily.query("symbol == 'BTCUSDT'").iloc[0]
    assert row.news_coverage_complete
    assert row.news_article_count == 0
    assert len(cleaned.articles) == 1
    assert cleaned.articles.retrieved_at.isna().all()
    assert len(cleaned.collections) == 1
