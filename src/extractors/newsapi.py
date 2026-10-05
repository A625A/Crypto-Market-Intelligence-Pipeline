"""Collect immutable per-asset NewsAPI snapshots with availability evidence."""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import time
from uuid import uuid4

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / '.env'
RAW_PATH = PROJECT_ROOT / 'data/raw/newsapi'
URL = 'https://newsapi.org/v2/everything'
QUERY_VERSION = 'direct-assets-v1'
CONTEXT = 'crypto OR cryptocurrency OR blockchain OR bitcoin OR ethereum OR solana'
QUERIES = {symbol: f'{name} OR ({symbol[:-4]} AND ({CONTEXT}))'
           for symbol, name in (('BTCUSDT', 'bitcoin'), ('ETHUSDT', 'ethereum'), ('SOLUSDT', 'solana'))}


def utc_now():
    return datetime.now(timezone.utc)


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Clock timestamps must be timezone-aware')
    return value.astimezone(timezone.utc)


def _validate_options(lookback_days, max_requests, cutoff_hour=23):
    if type(lookback_days) is not int or lookback_days < 1:
        raise ValueError('lookback_days must be a positive integer')
    if type(max_requests) is not int or not 1 <= max_requests <= 10:
        raise ValueError('max_requests must be an integer from 1 to 10')
    if type(cutoff_hour) is not int or not 0 <= cutoff_hour <= 23:
        raise ValueError('cutoff_hour must be an integer from 0 to 23')


def fetch_page(params, *, api_key, attempt_number):
    """Fetch one page; return JSON, safe attempt evidence and retry eligibility."""
    attempt = {'page': params['page'], 'attempt': attempt_number,
               'requested_at': _utc(utc_now()).isoformat(), 'http_status': None,
               'total_results': None, 'article_count': None, 'error': None}
    data = None
    retryable = False
    try:
        response = requests.get(URL, params=params, headers={'X-Api-Key': api_key}, timeout=30, allow_redirects=False)
        attempt['http_status'] = response.status_code
        retryable = 500 <= response.status_code <= 599
        try:
            data = response.json()
        except ValueError:
            attempt['error'] = 'invalid_json'
        if response.status_code != 200:
            attempt['error'] = f'http_{response.status_code}'
        if isinstance(data, dict):
            if data.get('status') != 'ok':
                attempt['error'] = str(data.get('code', 'api_error')).replace(api_key, '[REDACTED]')
            total = data.get('totalResults')
            attempt['total_results'] = total if type(total) is int else None
            if data.get('message') is not None:
                attempt['message'] = str(data['message']).replace(api_key, '[REDACTED]')
            if isinstance(data.get('articles'), list):
                attempt['article_count'] = len(data['articles'])
        elif not attempt['error']:
            attempt['error'] = 'invalid_response'
    except requests.RequestException as error:
        # Exception text may contain request headers/credentials. Store only its type.
        attempt['error'] = type(error).__name__
        retryable = isinstance(error, (requests.Timeout, requests.ConnectionError))
    attempt['responded_at'] = _utc(utc_now()).isoformat()
    return data, attempt, retryable


def collect_asset(symbol, *, api_key, run_id, started_at, lookback_days=3, max_requests=10):
    """Return a scan and an optional run-stop reason; availability awaits saving."""
    _validate_options(lookback_days, max_requests)
    started_at = _utc(started_at)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError('NEWSAPI_KEY must be nonempty')
    params = {'q': QUERIES[symbol], 'language': 'en', 'searchIn': 'title,description',
              'sortBy': 'publishedAt', 'pageSize': 100,
              'from': (started_at-timedelta(days=lookback_days)).isoformat(),
              'to': started_at.isoformat()}
    articles: list = []
    attempts: list[dict] = []
    total = None
    page, attempt_number = 1, 1
    seen_urls: set[str] = set()
    reason = 'request_budget_exhausted'
    stop_run = None
    while len(attempts) < max_requests:
        data, attempt, retryable = fetch_page(dict(params, page=page), api_key=api_key,
                                             attempt_number=attempt_number)
        attempts.append(attempt)
        if attempt['error']:
            reason = attempt['error']
            if (attempt['http_status'] in (401, 403, 429) or reason in
                    ('apiKeyDisabled', 'apiKeyExhausted', 'apiKeyInvalid', 'apiKeyMissing', 'rateLimited')):
                stop_run = reason
                break
            if retryable and attempt_number < 3 and len(attempts) < max_requests:
                time.sleep((2, 5)[attempt_number-1])
                attempt_number += 1
                continue
            break
        items = data.get('articles')
        reported_total = data.get('totalResults')
        if isinstance(items, list):
            articles.extend(items)
        if (type(reported_total) is not int or reported_total < 0
                or not isinstance(items, list) or len(items) > 100
                or any(not isinstance(item, dict) or not isinstance(item.get('url'), str)
                       for item in items)):
            reason = 'invalid_page'
            break
        if total is None:
            total = reported_total
        if data['totalResults'] != total:
            reason = 'total_results_changed'
            break
        urls = [item.get('url') for item in data['articles']]
        if len(articles) > total:
            reason = 'result_count_mismatch'
            break
        if len(set(urls)) != len(urls) or seen_urls.intersection(urls):
            reason = 'duplicate_articles'
            break
        seen_urls.update(urls)
        if len(articles) == total:
            reason = 'complete'
            break
        if not data['articles']:
            reason = 'premature_empty_page'
            break
        page += 1
        attempt_number = 1
        reason = 'request_budget_exhausted'
    status = 'success' if reason == 'complete' else ('incomplete' if total is not None or reason == 'invalid_page' else 'failed')
    return {'run_id': run_id, 'symbol': symbol, 'query': QUERIES[symbol],
            'query_version': QUERY_VERSION, 'search_parameters': params,
            'run_started_at': started_at.isoformat(), 'retrieved_at': None,
            'status': status, 'stop_reason': reason, 'attempts': attempts,
            'response': {'status': 'ok' if total is not None or reason == 'invalid_page' else 'error',
                         'totalResults': total, 'articles': articles}}, stop_run


def _write_json(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save_snapshot(scan, run_dir, *, cutoff_hour=23):
    """Durably preserve the payload before recording its UTC availability.

    A private checkpoint proves preservation before the final envelope is
    stamped. A hard link publishes the finished JSON atomically without replacing
    an existing snapshot. Only the finished asset JSON is a cleaner input.
    """
    from tempfile import TemporaryDirectory

    if scan['symbol'] not in QUERIES:
        raise ValueError('Unknown asset')
    if type(cutoff_hour) is not int or not 0 <= cutoff_hour <= 23:
        raise ValueError('cutoff_hour must be an integer from 0 to 23')
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / f"{scan['symbol']}.json"
    with TemporaryDirectory(prefix='.pending-', dir=run_dir) as temporary_name:
        temporary = Path(temporary_name)
        _write_json(temporary / 'payload.json', {'collections': [scan]})
        _sync_directory(temporary)
        _sync_directory(run_dir)
        received = _utc(utc_now())
        observed = [scan['run_started_at']] + [row['responded_at'] for row in scan['attempts']]
        if received < max(datetime.fromisoformat(value) for value in observed):
            raise ValueError('Preservation clock moved before recorded receipt')
        end = received.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
        if received > end:
            end += timedelta(days=1)
        saved = dict(scan, retrieved_at=received.isoformat(),
                     window_start=(end-timedelta(days=1)).isoformat(), window_end=end.isoformat())
        completed = temporary / 'snapshot.json'
        _write_json(completed, {'collections': [saved]})
        os.link(completed, output_path)
        _sync_directory(run_dir)
    return output_path


def collect_news(output_dir=RAW_PATH, *, api_key=None, lookback_days=3, max_requests=10, cutoff_hour=23):
    """Collect and preserve each asset before starting the next; return snapshot paths."""
    _validate_options(lookback_days, max_requests, cutoff_hour)
    if api_key is None:
        load_dotenv(dotenv_path=ENV_PATH, override=False)
        api_key = os.getenv('NEWSAPI_KEY')
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError('NEWSAPI_KEY not found in environment variables.')
    started_at = _utc(utc_now())
    run_id = f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex}"
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    _sync_directory(run_dir.parent)
    paths = []
    stop = None
    for symbol in QUERIES:
        if stop:
            # Carry run/search bounds forward, but never another asset's articles.
            scan = dict(scan, symbol=symbol, query=QUERIES[symbol],
                        search_parameters=dict(scan['search_parameters'], q=QUERIES[symbol]),
                        status='failed', stop_reason=f'skipped_after:{stop}', attempts=[],
                        response={'status': 'error', 'totalResults': None, 'articles': []})
        else:
            scan, stop = collect_asset(symbol, api_key=api_key, run_id=run_id,
                                       started_at=started_at, lookback_days=lookback_days,
                                       max_requests=max_requests)
        path = save_snapshot(scan, run_dir, cutoff_hour=cutoff_hour)
        logger.info('%s: %s (%s); %s requests, %s articles; saved %s',
                    symbol, scan['status'], scan['stop_reason'], len(scan['attempts']),
                    len(scan['response']['articles']), path)
        paths.append(path)
    return paths


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=RAW_PATH)
    parser.add_argument('--lookback-days', type=int, default=3)
    parser.add_argument('--max-requests', type=int, default=10,
                        help='Per-asset allowance including retries (1-10)')
    parser.add_argument('--cutoff-hour', type=int, default=23)
    args = parser.parse_args(argv)
    try:
        paths = collect_news(args.output_dir, lookback_days=args.lookback_days,
                             max_requests=args.max_requests, cutoff_hour=args.cutoff_hour)
    except (ValueError, OSError) as error:
        logger.error('Collection could not finish: %s', error)
        return 1
    complete = all(json.loads(path.read_text())['collections'][0]['status'] == 'success'
                   for path in paths)
    logger.info('Run finished: %s snapshots; all scans complete: %s', len(paths), complete)
    return 0 if complete else 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    raise SystemExit(main())
