"""Availability-window news activity and financial-tone features."""

from dataclasses import dataclass
import math
import logging
from pathlib import Path
import sys
import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ''):
    sys.path.insert(0, str(PROJECT_ROOT))

from src.transformers.clean_newsapi import CleanNews, SYMBOLS
from src.features.news_sentiment import ToneScorer

logger = logging.getLogger(__name__)

TONE_LABELS = ('positive', 'negative', 'neutral')


@dataclass
class NewsFeatures:
    daily: pd.DataFrame
    articles: pd.DataFrame


def _story_ids(articles):
    representatives: list[tuple[Any, str]] = []
    assignments = {}
    for row in articles.sort_values(['published_at', 'article_id']).itertuples():
        title = ' '.join(re.findall(r'\w+', row.title.casefold()))
        story_id = row.article_id
        for representative, headline in representatives:
            proximity = abs(row.published_at - representative.published_at) <= pd.Timedelta(hours=36)
            if proximity and SequenceMatcher(None, title, headline).ratio() >= 0.92:
                story_id = representative.article_id
                break
        else:
            representatives.append((row, title))
        assignments[row.article_id] = story_id
    return articles.article_id.map(assignments)


def build_news_features(cleaned: CleanNews, dates, *, scorer: ToneScorer, cutoff_hour=23) -> NewsFeatures:
    """Build requested UTC date/asset rows using first retrieval by cutoff."""
    dates = pd.to_datetime(list(dates), utc=True)
    if (dates.empty or dates.isna().any() or dates.has_duplicates
            or not dates.equals(dates.normalize())):
        raise ValueError('dates must be unique UTC midnight dates')
    if isinstance(cutoff_hour, bool) or not isinstance(cutoff_hour, int) or not 0 <= cutoff_hour <= 23:
        raise ValueError('cutoff_hour must be an integer from 0 to 23')
    rows, selected = [], []
    for date in dates.sort_values():
        cutoff = date + pd.Timedelta(hours=cutoff_hour)
        start = cutoff - pd.Timedelta(days=1)
        for symbol in SYMBOLS:
            scans = cleaned.collections
            # Missing evidence must not disappear beside a successful scan.
            # Unknown asset scope may affect every asset; unknown window bounds
            # may affect any matching window in which the scan was observed.
            asset_matches = scans.symbol.eq(symbol) | ~scans.symbol.isin(SYMBOLS)
            window_matches = (scans.window_start.eq(start) | scans.window_start.isna()) & (
                scans.window_end.eq(cutoff) | scans.window_end.isna())
            no_window = scans.window_start.isna() & scans.window_end.isna()
            window_matches &= ~no_window | scans.retrieved_at.isna() | scans.retrieved_at.gt(start)
            observed = scans.retrieved_at.le(cutoff) | scans.retrieved_at.isna()
            scans = scans.loc[asset_matches & window_matches & observed]
            complete = not scans.empty and scans.status.eq('success').all()
            articles = cleaned.articles
            articles = articles.loc[(articles.symbol == symbol)
                & (articles.first_retrieved_at > start) & (articles.first_retrieved_at <= cutoff)
                & (articles.retrieved_at <= cutoff)]
            articles = articles.sort_values('retrieved_at').drop_duplicates('article_id', keep='last')
            articles = articles.copy()
            articles['story_id'] = _story_ids(articles)
            for field in ('title', 'description'):
                for label in TONE_LABELS:
                    articles[f'{field}_{label}'] = float('nan')
                present = articles[field].notna()
                if complete and present.any():
                    scores = scorer.score(articles.loc[present, field].tolist())
                    if len(scores) != int(present.sum()):
                        raise ValueError('Invalid sentiment result count')
                    for score in scores:
                        if (set(score) != set(TONE_LABELS)
                                or any(not math.isfinite(value) or not 0 <= value <= 1 for value in score.values())
                                or not math.isclose(sum(score.values()), 1.0, abs_tol=1e-5)):
                            raise ValueError('Invalid sentiment probability vector')
                    for label in TONE_LABELS:
                        articles.loc[present, f'{field}_{label}'] = [score[label] for score in scores]
            row = {'symbol': symbol, 'date': date.tz_localize(None), 'news_cutoff_at': cutoff,
                   'news_coverage_complete': complete, 'news_article_count': None,
                   'news_article_age_hours_mean': None, 'news_unique_source_count': None,
                   'estimated_distinct_story_count': None, 'news_repeated_coverage_count': None,
                   'news_time_since_first_retrieval_hours_mean': None}
            for field in ('title', 'description'):
                row[f'news_{field}_scored_count'] = None
                for label in TONE_LABELS:
                    row[f'news_{field}_{label}_mean'] = None
            if complete:
                for field in ('title', 'description'):
                    row[f'news_{field}_scored_count'] = int(articles[f'{field}_positive'].notna().sum())
                    for label in TONE_LABELS:
                        row[f'news_{field}_{label}_mean'] = articles[f'{field}_{label}'].mean()
                row['news_article_count'] = len(articles)
                row['news_unique_source_count'] = articles.source.str.casefold().nunique()
                row['estimated_distinct_story_count'] = articles.story_id.nunique()
                row['news_repeated_coverage_count'] = len(articles) - articles.story_id.nunique()
                row['news_time_since_first_retrieval_hours_mean'] = (cutoff-articles.first_retrieved_at).dt.total_seconds().mean()/3600
                row['news_article_age_hours_mean'] = (cutoff-articles.published_at).dt.total_seconds().mean()/3600
                selected.append(articles.assign(date=date.tz_localize(None)))
            rows.append(row)
    daily = pd.DataFrame(rows)
    for column in map(str, daily.columns):
        if column.endswith('_count'):
            daily[column] = daily[column].astype('Int64')
        elif column.endswith('_mean'):
            daily[column] = daily[column].astype('float64')
    scored_articles = (pd.concat(selected, ignore_index=True) if selected
                       else articles.iloc[:0].assign(date=pd.Series(dtype='datetime64[ns]')))
    return NewsFeatures(daily, scored_articles)


def create_news_features(clean_dir, output_dir, start_date, end_date, *, scorer=None, cutoff_hour=23) -> NewsFeatures:
    """Read cleaned history and save daily/article features only after a valid build."""
    import json
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from src.features.news_sentiment import FinBertScorer

    clean_dir, output_dir = Path(clean_dir), Path(output_dir)
    cleaned = CleanNews(*(pd.read_parquet(clean_dir/f'{name}.parquet')
                          for name in ('articles', 'collections', 'rejected')))
    scorer = scorer if scorer is not None else FinBertScorer()
    result = build_news_features(cleaned, pd.date_range(start_date, end_date, freq='D'),
                                 scorer=scorer, cutoff_hour=cutoff_hour)
    metadata = {'scorer': scorer.metadata, 'news_cutoff_hour_utc': cutoff_hour,
                'window': '(previous cutoff, current cutoff]', 'rules': 'news-v1',
                'story_similarity': 0.92, 'story_proximity_hours': 36}
    result.daily.attrs.update(metadata)
    result.articles.attrs.update(metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir) as temporary:
        temporary = Path(temporary)
        result.daily.to_parquet(temporary/'news_features.parquet', index=False)
        result.articles.to_parquet(temporary/'article_features.parquet', index=False)
        (temporary/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
        for path in temporary.iterdir():
            path.replace(output_dir/path.name)
    return result


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    from src.features.news_sentiment import FinBertScorer

    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean-dir', type=Path, default=root/'data/processed/newsapi')
    parser.add_argument('--output-dir', type=Path, default=root/'data/processed/features/newsapi')
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--cutoff-hour', type=int, default=23)
    parser.add_argument('--offline-model', action='store_true', help='Require already cached FinBERT weights')
    arguments = parser.parse_args()
    output = create_news_features(arguments.clean_dir, arguments.output_dir,
                                  arguments.start_date, arguments.end_date,
                                  scorer=FinBertScorer(local_files_only=arguments.offline_model),
                                  cutoff_hour=arguments.cutoff_hour)
    logger.info('Created %s daily asset rows.', len(output.daily))
