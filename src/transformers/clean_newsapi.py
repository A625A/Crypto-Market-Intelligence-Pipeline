"""Clean recorded NewsAPI responses without inventing historical availability."""

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT')
ARTICLE_COLUMNS = ['article_id', 'version_id', 'symbol', 'source', 'url', 'title',
                   'description', 'published_at', 'retrieved_at', 'first_retrieved_at']
COLLECTION_COLUMNS = ['run_id', 'symbol', 'query', 'window_start', 'window_end',
                      'retrieved_at', 'status', 'reason']
REJECTED_COLUMNS = ['run_id', 'record_index', 'reason', 'raw_article']


@dataclass
class CleanNews:
    articles: pd.DataFrame
    collections: pd.DataFrame
    rejected: pd.DataFrame


def _hash(value):
    return sha256(value.encode('utf-8')).hexdigest()


def _timestamp(value):
    if not isinstance(value, (str, pd.Timestamp)):
        return pd.NaT
    try:
        timestamp = pd.Timestamp(value)
        return timestamp.tz_convert('UTC') if timestamp.tzinfo else pd.NaT
    except (ValueError, TypeError):
        return pd.NaT


def _text(value):
    return ' '.join(value.split()) if isinstance(value, str) and value.strip() else None


def _canonical_url(url):
    if not isinstance(url, str):
        raise ValueError('missing article URL')
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
        raise ValueError('invalid article URL')
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith('utm_') and key.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path,
                       urlencode(sorted(query)), ''))


def _article(item, retrieved_at):
    if not isinstance(item, dict):
        raise ValueError('article must be an object')
    url = _canonical_url(item.get('url'))
    title = _text(item.get('title'))
    description = _text(item.get('description'))
    if not title or title.lower() == '[removed]':
        raise ValueError('missing or removed title')
    if description and description.lower() == '[removed]':
        description = None
    published_at = _timestamp(item.get('publishedAt'))
    if pd.isna(published_at):
        raise ValueError('publication timestamp must include a timezone')
    if pd.notna(retrieved_at) and published_at > retrieved_at:
        raise ValueError('publication timestamp is after retrieval')
    source = item.get('source') or {}
    source = _text(source.get('name')) if isinstance(source, dict) else None
    source = source or urlsplit(url).hostname
    version = [url, title, description, published_at.isoformat(), source]
    return {'article_id': _hash(url), 'version_id': _hash(json.dumps(version)),
            'source': source, 'url': url, 'title': title, 'description': description,
            'published_at': published_at, 'retrieved_at': retrieved_at}


def clean_newsapi(raw: dict) -> CleanNews:
    """Return immutable article versions, collection evidence and rejection reasons.

    Input is a collections envelope or the legacy symbol-to-response mapping.
    Retrieval timestamps must explicitly represent successful preservation;
    this transformer never generates or infers them.
    """
    if not isinstance(raw, dict):
        raise ValueError('NewsAPI input must be an object')
    collections = raw.get('collections')
    legacy = collections is None
    if legacy:
        collections = [{'response': value} for key, value in raw.items() if key in SYMBOLS]
    if not isinstance(collections, list):
        raise ValueError('collections must be a list')
    rows, scans, rejected = [], [], []
    for collection in collections:
        received = _timestamp(collection.get('retrieved_at'))
        evidence = {key: collection.get(key) for key in COLLECTION_COLUMNS}
        evidence['retrieved_at'] = received
        evidence['reason'] = ''
        for key in ('window_start', 'window_end'):
            evidence[key] = _timestamp(collection.get(key))
        response = collection.get('response') or {}
        if not isinstance(response, dict):
            raise ValueError('response must be an object')
        if not legacy:
            missing_evidence = (not _text(evidence['run_id']) or not _text(evidence['query'])
                or evidence['symbol'] not in SYMBOLS or pd.isna(received)
                or pd.isna(evidence['window_start']) or pd.isna(evidence['window_end']))
            if missing_evidence or evidence['status'] not in ('success', 'incomplete', 'failed'):
                evidence.update(status='incomplete', reason='missing or invalid collection evidence')
            elif evidence['window_start'] >= evidence['window_end'] or received <= evidence['window_start']:
                evidence.update(status='incomplete', reason='invalid collection interval')
            if response.get('status') != 'ok':
                evidence.update(status='failed', reason='NewsAPI response was not successful')
            total = response.get('totalResults')
            if not isinstance(total, int) or isinstance(total, bool) or total < 0 or total > len(response.get('articles', [])):
                if evidence['status'] != 'failed':
                    evidence.update(status='incomplete', reason='unverified or truncated result count')
        for index, item in enumerate(response.get('articles', [])):
            try:
                row = _article(item, received)
            except ValueError as error:
                rejected.append({'run_id': collection.get('run_id'), 'record_index': index,
                                 'reason': str(error), 'raw_article': json.dumps(item)})
                evidence['status'] = 'incomplete'
                evidence['reason'] = 'rejected article'
                continue
            text = f"{row['title']} {row['description'] or ''}"
            crypto_context = re.search(r'\b(crypto|cryptocurrency|blockchain|bitcoin|ethereum|solana)\b', text, re.I)
            for symbol, name in zip(SYMBOLS, ('bitcoin', 'ethereum', 'solana')):
                named = re.search(rf'\b{name}\b', text, re.I)
                ticker = re.search(rf'\b{symbol[:-4]}\b', text)
                if named or (ticker and crypto_context):
                    rows.append(dict(row, symbol=symbol))
        if not legacy:
            scans.append(evidence)
    articles = pd.DataFrame(rows, columns=ARTICLE_COLUMNS[:-1])
    for key in ('published_at', 'retrieved_at'):
        articles[key] = pd.to_datetime(articles[key], utc=True)
    articles = articles.sort_values(['retrieved_at', 'article_id', 'version_id']).drop_duplicates(
        ['article_id', 'version_id', 'symbol'])
    articles['first_retrieved_at'] = articles.groupby(['article_id', 'symbol'])['retrieved_at'].transform('min')
    scan_frame = pd.DataFrame(scans, columns=COLLECTION_COLUMNS)
    for key in ('window_start', 'window_end', 'retrieved_at'):
        scan_frame[key] = pd.to_datetime(scan_frame[key], utc=True)
    return CleanNews(articles.reset_index(drop=True),
                     scan_frame,
                     pd.DataFrame(rejected, columns=REJECTED_COLUMNS))


def create_clean_newsapi(raw_paths, output_dir) -> CleanNews:
    """Clean the complete supplied snapshot history and save article/audit tables."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    records = []
    for path in raw_paths:
        raw = json.loads(Path(path).read_text())
        if 'collections' in raw:
            records.extend(raw['collections'])
        else:
            records.extend({'symbol': symbol, 'response': response}
                           for symbol, response in raw.items() if symbol in SYMBOLS)
    cleaned = clean_newsapi({'collections': records})
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir) as temporary:
        for name in ('articles', 'collections', 'rejected'):
            getattr(cleaned, name).to_parquet(Path(temporary)/f'{name}.parquet', index=False)
        for path in Path(temporary).iterdir():
            path.replace(output_dir/path.name)
    return cleaned


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--input',
        type=Path,
        action='append',
        help='Saved snapshot; repeat to supply the complete history'
    )
    parser.add_argument('--output-dir', type=Path, default=root/'data/processed/newsapi')
    arguments = parser.parse_args()

    input_paths = arguments.input or [
        root / 'data/raw/newsapi_raw.json'
    ]

    output = create_clean_newsapi(
        input_paths,
        arguments.output_dir
    )

    logger.info(
        "Cleaned %s article/asset versions; %s rejected records.",
        len(output.articles),
        len(output.rejected)
    )