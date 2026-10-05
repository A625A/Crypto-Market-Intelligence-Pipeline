"""Collector behavior through fake HTTP and the public collection interfaces."""

from datetime import datetime, timezone

import pytest

from src.extractors import newsapi


NOW = datetime(2026, 10, 4, 22, 45, tzinfo=timezone.utc)


def article(index=0):
    return {'source': {'name': 'Example'}, 'url': f'https://example.com/{index}',
            'title': 'Bitcoin Ethereum Solana adoption grows', 'description': None,
            'publishedAt': '2026-10-02T12:00:00Z'}


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


def install_http(monkeypatch, replies):
    calls = []
    replies = iter(replies)

    def get(url, **kwargs):
        calls.append(kwargs)
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(newsapi.requests, 'get', get)
    monkeypatch.setattr(newsapi, 'utc_now', lambda: NOW)
    return calls


def test_single_page_scan_preserves_contract_and_search_parameters(monkeypatch):
    calls = install_http(monkeypatch, [Response({'status': 'ok', 'totalResults': 1,
                                               'articles': [article()]})])
    scan, stop = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                      run_id='test-run', started_at=NOW)
    assert stop is None
    assert scan['status'] == 'success'
    assert scan['response']['articles'] == [article()]
    assert scan['run_id'] == 'test-run'
    assert scan['retrieved_at'] is None  # HTTP receipt is not durable preservation.
    assert scan['attempts'][0]['article_count'] == 1
    params = calls[0]['params']
    assert params['from'] == '2026-10-01T22:45:00+00:00'
    assert params['to'] == NOW.isoformat()
    assert params['searchIn'] == 'title,description'
    assert params['pageSize'] == 100
    assert params['page'] == 1
    assert params['q'] == newsapi.QUERIES['BTCUSDT']
    assert calls[0]['timeout'] == 30


def test_pagination_combines_pages_and_stops_at_reported_total(monkeypatch):
    first = [article(index) for index in range(100)]
    calls = install_http(monkeypatch, [
        Response({'status': 'ok', 'totalResults': 101, 'articles': first}),
        Response({'status': 'ok', 'totalResults': 101, 'articles': [article(100)]})])
    scan, _ = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                    run_id='test-run', started_at=NOW)
    assert scan['status'] == 'success'
    assert len(scan['response']['articles']) == 101
    assert [call['params']['page'] for call in calls] == [1, 2]
    assert [row['article_count'] for row in scan['attempts']] == [100, 1]


def test_truncated_scan_is_incomplete_when_budget_is_exhausted(monkeypatch):
    calls = install_http(monkeypatch, [Response({'status': 'ok', 'totalResults': 101,
                                               'articles': [article(i) for i in range(100)]})])
    scan, _ = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                    run_id='test-run', started_at=NOW, max_requests=1)
    assert scan['status'] == 'incomplete'
    assert scan['stop_reason'] == 'request_budget_exhausted'
    assert len(calls) == 1
    assert scan['response']['totalResults'] == 101
    assert len(scan['response']['articles']) == 100


def test_transient_failures_retry_same_page_within_budget(monkeypatch):
    import requests
    calls = install_http(monkeypatch, [requests.Timeout('test-secret'),
        Response({'status': 'error', 'message': 'test-secret'}, 503),
        Response({'status': 'ok', 'totalResults': 0, 'articles': []})])
    sleeps = []
    monkeypatch.setattr(newsapi.time, 'sleep', sleeps.append)
    scan, stop = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                      run_id='test-run', started_at=NOW)
    assert scan['status'] == 'success'
    assert stop is None
    assert sleeps == [2, 5]
    assert len(calls) == 3
    assert [row['attempt'] for row in scan['attempts']] == [1, 2, 3]
    assert 'test-secret' not in str(scan)


def test_rate_limit_stops_without_retry_and_redacts_provider_errors(monkeypatch):
    calls = install_http(monkeypatch, [Response({'status': 'error',
        'code': 'rateLimited', 'message': 'key test-secret exhausted'}, 429)])
    scan, stop = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                      run_id='test-run', started_at=NOW)
    assert stop == 'rateLimited'
    assert scan['status'] == 'failed'
    assert len(calls) == 1
    assert 'test-secret' not in str(scan)


def test_changed_totals_and_repeated_articles_cannot_prove_complete_scan(monkeypatch):
    calls = install_http(monkeypatch, [
        Response({'status': 'ok', 'totalResults': 101, 'articles': [article(i) for i in range(100)]}),
        Response({'status': 'ok', 'totalResults': 100, 'articles': [article(0)]})])
    scan, _ = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                    run_id='test-run', started_at=NOW)
    assert scan['status'] == 'incomplete'
    assert scan['stop_reason'] == 'total_results_changed'
    assert scan['response']['totalResults'] == 101
    assert len(scan['response']['articles']) == 101  # Preserve the received evidence.
    assert len(calls) == 2


@pytest.mark.parametrize('second,total,reason', [
    ([article(0)], 101, 'duplicate_articles'),
    ([], 101, 'premature_empty_page'),
    ([article(100), article(101)], 101, 'result_count_mismatch'),
])
def test_pagination_anomalies_preserve_partial_data(monkeypatch, second, total, reason):
    calls = install_http(monkeypatch, [
        Response({'status': 'ok', 'totalResults': total, 'articles': [article(i) for i in range(100)]}),
        Response({'status': 'ok', 'totalResults': total, 'articles': second})])
    scan, _ = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                    run_id='test-run', started_at=NOW)
    assert scan['status'] == 'incomplete'
    assert scan['stop_reason'] == reason
    assert len(scan['response']['articles']) == 100 + len(second)
    assert len(calls) == 2


@pytest.mark.parametrize('body', [
    {'status': 'ok', 'totalResults': 0},
    {'status': 'ok', 'totalResults': True, 'articles': []},
    {'status': 'ok', 'totalResults': -1, 'articles': []},
    {'status': 'ok', 'totalResults': 1, 'articles': [None]},
    {'status': 'ok', 'totalResults': 1, 'articles': [{'url': ['bad']}]},
])
def test_malformed_page_is_not_successful_zero_news(monkeypatch, body):
    install_http(monkeypatch, [Response(body)])
    scan, stop = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                      run_id='test-run', started_at=NOW)
    assert stop is None
    assert scan['status'] == 'incomplete'
    assert scan['stop_reason'] == 'invalid_page'


def test_saved_scan_uses_durable_preservation_time_and_next_cutoff(monkeypatch, tmp_path):
    import json
    import os
    install_http(monkeypatch, [Response({'status': 'ok', 'totalResults': 1,
                                        'articles': [article()]})])
    scan, _ = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                    run_id='test-run', started_at=NOW)
    saved_at = datetime(2026, 10, 4, 23, 0, 1, tzinfo=timezone.utc)
    clock = [NOW]
    fsync = os.fsync

    def sync_then_advance(fd):
        fsync(fd)
        clock[0] = saved_at

    monkeypatch.setattr(newsapi.os, 'fsync', sync_then_advance)
    monkeypatch.setattr(newsapi, 'utc_now', lambda: clock[0])
    path = newsapi.save_snapshot(scan, tmp_path)
    saved = json.loads(path.read_text())['collections'][0]
    assert saved['retrieved_at'] == '2026-10-04T23:00:01+00:00'
    assert saved['window_start'] == '2026-10-04T23:00:00+00:00'
    assert saved['window_end'] == '2026-10-05T23:00:00+00:00'
    assert saved['response'] == scan['response']
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        newsapi.save_snapshot(scan, tmp_path)
    assert path.read_bytes() == original


def test_run_saves_each_asset_and_continues_after_asset_failure(monkeypatch, tmp_path):
    import json
    replies = [Response({'status': 'error', 'code': 'parameterInvalid'}, 400),
               Response({'status': 'ok', 'totalResults': 0, 'articles': []}),
               Response({'status': 'ok', 'totalResults': 1, 'articles': [article()]})]
    calls = install_http(monkeypatch, replies)
    paths = newsapi.collect_news(tmp_path, api_key='test-secret')
    scans = [json.loads(path.read_text())['collections'][0] for path in paths]
    assert len(calls) == 3
    assert [scan['symbol'] for scan in scans] == ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    assert [scan['status'] for scan in scans] == ['failed', 'success', 'success']
    assert len({scan['run_id'] for scan in scans}) == 1
    assert len({path.parent for path in paths}) == 1
    assert all(scan['retrieved_at'] == NOW.isoformat() for scan in scans)


@pytest.mark.parametrize('http_status,code', [(429, 'rateLimited'), (401, 'apiKeyInvalid'),
                                              (403, 'apiKeyExhausted'), (200, 'apiKeyDisabled')])
def test_shared_failure_stops_run_and_saves_unattempted_outcomes(monkeypatch, tmp_path, http_status, code):
    import json
    calls = install_http(monkeypatch, [Response({'status': 'error', 'code': code}, http_status)])
    paths = newsapi.collect_news(tmp_path, api_key='test-secret')
    scans = [json.loads(path.read_text())['collections'][0] for path in paths]
    assert len(calls) == 1
    assert len(scans) == 3
    assert all(scan['status'] == 'failed' for scan in scans)
    assert scans[1]['attempts'] == []
    assert scans[1]['stop_reason'] == f'skipped_after:{code}'
    assert scans[2]['symbol'] == 'SOLUSDT'
    assert scans[2]['search_parameters']['q'] == newsapi.QUERIES['SOLUSDT']


@pytest.mark.parametrize('options', [{'max_requests': 11}, {'max_requests': 0},
    {'max_requests': True}, {'lookback_days': 0}, {'lookback_days': 1.5}, {'cutoff_hour': 24}])
def test_invalid_options_fail_before_network_or_snapshot_creation(monkeypatch, tmp_path, options):
    calls = install_http(monkeypatch, [])
    with pytest.raises(ValueError):
        newsapi.collect_news(tmp_path, api_key='test-secret', **options)
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_cli_reports_incomplete_run_after_saving_all_outcomes(monkeypatch, tmp_path):
    install_http(monkeypatch, [Response({'status': 'ok', 'totalResults': 101,
        'articles': [article(i) for i in range(100)]}),
        Response({'status': 'ok', 'totalResults': 0, 'articles': []}),
        Response({'status': 'ok', 'totalResults': 0, 'articles': []})])
    monkeypatch.setenv('NEWSAPI_KEY', 'test-secret')
    assert newsapi.main(['--output-dir', str(tmp_path), '--max-requests', '1']) == 1
    assert len(list(tmp_path.glob('*/*.json'))) == 3


def test_collector_snapshots_flow_through_cleaner_and_daily_features(monkeypatch, tmp_path):
    import pandas as pd
    from src.transformers.clean_newsapi import create_clean_newsapi
    from src.features.news_features import build_news_features

    class Tone:
        def score(self, texts):
            return [{'positive': 0.8, 'negative': 0.1, 'neutral': 0.1} for _ in texts]

    btc = dict(article(), title='Bitcoin adoption grows')
    install_http(monkeypatch, [Response({'status': 'ok', 'totalResults': 1, 'articles': [btc]}),
        Response({'status': 'ok', 'totalResults': 0, 'articles': []}),
        Response({'status': 'error', 'code': 'parameterInvalid'}, 400)])
    paths = newsapi.collect_news(tmp_path/'raw', api_key='test-secret')
    cleaned = create_clean_newsapi(paths, tmp_path/'clean')
    result = build_news_features(cleaned, ['2026-10-04'], scorer=Tone()).daily.set_index('symbol')
    assert cleaned.rejected.empty
    assert len(cleaned.collections) == 3
    assert result.loc['BTCUSDT', 'news_article_count'] == 1
    assert result.loc['BTCUSDT', 'news_title_positive_mean'] == 0.8
    assert pd.isna(result.loc['BTCUSDT', 'news_description_positive_mean'])
    assert result.loc['ETHUSDT', 'news_article_count'] == 0
    assert result.loc['ETHUSDT', 'news_coverage_complete']
    assert not result.loc['SOLUSDT', 'news_coverage_complete']
    assert pd.isna(result.loc['SOLUSDT', 'news_article_count'])


@pytest.mark.parametrize('failure', [Response({'status': 'error', 'code': 'maximumResultsReached'}, 400),
                                   Response({'status': 'error'}, 503)])
def test_later_page_failure_preserves_first_page_and_stays_incomplete(monkeypatch, failure):
    replies = [Response({'status': 'ok', 'totalResults': 101,
                         'articles': [article(i) for i in range(100)]}), failure, failure, failure]
    calls = install_http(monkeypatch, replies)
    sleeps = []
    monkeypatch.setattr(newsapi.time, 'sleep', sleeps.append)
    scan, stop = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                      run_id='test-run', started_at=NOW)
    assert stop is None
    assert scan['status'] == 'incomplete'
    assert len(scan['response']['articles']) == 100
    assert scan['response']['totalResults'] == 101
    assert len(calls) == (4 if failure.status_code == 503 else 2)
    assert sleeps == ([2, 5] if failure.status_code == 503 else [])


def test_retry_cannot_exceed_remaining_request_budget(monkeypatch):
    import requests
    calls = install_http(monkeypatch, [requests.ConnectionError('test-secret')] * 2)
    sleeps = []
    monkeypatch.setattr(newsapi.time, 'sleep', sleeps.append)
    scan, _ = newsapi.collect_asset('BTCUSDT', api_key='test-secret',
                                    run_id='test-run', started_at=NOW, max_requests=2)
    assert scan['status'] == 'failed'
    assert len(calls) == 2
    assert sleeps == [2]


def test_same_time_runs_get_distinct_directories_without_overwriting(monkeypatch, tmp_path):
    import json
    replies = [Response({'status': 'ok', 'totalResults': 0, 'articles': []}) for _ in range(6)]
    install_http(monkeypatch, replies)
    first = newsapi.collect_news(tmp_path, api_key='test-secret')
    before = [path.read_bytes() for path in first]
    second = newsapi.collect_news(tmp_path, api_key='test-secret')
    assert first[0].parent != second[0].parent
    assert [path.read_bytes() for path in first] == before
    assert len(list(tmp_path.glob('*/*.json'))) == 6
    assert all(json.loads(path.read_text())['collections'][0]['status'] == 'success' for path in second)


@pytest.mark.parametrize('saved_at,expected_end', [
    (datetime(2026, 10, 4, 23, tzinfo=timezone.utc), '2026-10-04T23:00:00+00:00'),
    (datetime(2026, 10, 4, 23, 0, 0, 1, tzinfo=timezone.utc), '2026-10-05T23:00:00+00:00'),
])
def test_exact_preservation_cutoff_is_inclusive(monkeypatch, tmp_path, saved_at, expected_end):
    import json
    install_http(monkeypatch, [Response({'status': 'ok', 'totalResults': 0, 'articles': []})])
    scan, _ = newsapi.collect_asset('BTCUSDT', api_key='test-secret', run_id='run', started_at=NOW)
    monkeypatch.setattr(newsapi, 'utc_now', lambda: saved_at)
    saved = json.loads(newsapi.save_snapshot(scan, tmp_path).read_text())['collections'][0]
    assert saved['window_end'] == expected_end


def test_later_persistence_failure_preserves_previously_saved_assets(monkeypatch, tmp_path):
    import os
    install_http(monkeypatch, [Response({'status': 'ok', 'totalResults': 0, 'articles': []})] * 2)
    link = os.link

    def fail_second_asset(source, destination):
        if destination.name == 'ETHUSDT.json':
            raise OSError('simulated disk failure')
        link(source, destination)

    monkeypatch.setattr(newsapi.os, 'link', fail_second_asset)
    with pytest.raises(OSError, match='simulated disk failure'):
        newsapi.collect_news(tmp_path, api_key='test-secret')
    assert len(list(tmp_path.glob('*/BTCUSDT.json'))) == 1
    assert list(tmp_path.glob('*/ETHUSDT.json')) == []
    assert list(tmp_path.glob('*/SOLUSDT.json')) == []
