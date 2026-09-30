"""Pinned local financial-tone scoring; no hosted inference or API credentials."""

from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol, Sequence

MODEL_ID = 'ProsusAI/finbert'
MODEL_REVISION = '4556d13015211d73dccd3fdd39d39232506f3e43'
MODEL_CACHE = Path(__file__).resolve().parents[2] / 'models' / 'news-finbert'


class ToneScorer(Protocol):
    @property
    def metadata(self) -> dict: ...

    def score(self, texts: Sequence[str]) -> list[dict[str, float]]: ...


class FinBertScorer:
    """CPU FinBERT adapter. First use downloads only this pinned public checkpoint.

    Empty/missing text is handled by the caller, not converted to neutral tone.
    Financial-tone outputs are not probabilities of asset price movements.
    """

    def __init__(self, *, cache_dir=MODEL_CACHE, local_files_only=False):
        self.cache_dir = Path(cache_dir)
        self.local_files_only = local_files_only
        self._model = None
        self._tokenizer: Any = None

    @property
    def metadata(self) -> dict:
        return {'model_id': MODEL_ID, 'revision': MODEL_REVISION,
                'tokenizer_revision': MODEL_REVISION, 'preprocessing': 'whitespace-v1; truncate-512',
                'torch': version('torch'), 'transformers': version('transformers'),
                'tokenizers': version('tokenizers')}

    def score(self, texts: Sequence[str]) -> list[dict[str, float]]:
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError('FinBERT requires nonempty text')
        if not texts:
            return []
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if self._model is None:
            options = dict(revision=MODEL_REVISION, cache_dir=self.cache_dir,
                           local_files_only=self.local_files_only, trust_remote_code=False,
                           token=False)
            self._tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, **options)
            self._model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, **options)
            self._model.eval()
        result: list[dict[str, float]] = []
        with torch.inference_mode():
            for start in range(0, len(texts), 16):
                inputs = self._tokenizer(list(texts[start:start+16]), return_tensors='pt',
                                         padding=True, truncation=True, max_length=512)
                scores = self._model(**inputs).logits.softmax(dim=-1).tolist()
                result.extend({self._model.config.id2label[index].lower(): value
                               for index, value in enumerate(row)} for row in scores)
        return result
