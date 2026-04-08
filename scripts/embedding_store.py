"""Local embedding model wrapper and vector storage.

Uses SentenceTransformer (jinaai/jina-embeddings-v5-text-nano) for zero-cost
local embeddings. Stores vectors as .npy files with parallel JSON metadata.

Patterns adapted from zotero-arxiv-daily local reranker.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "jinaai/jina-embeddings-v5-text-nano"
DEFAULT_ENCODE_KWARGS = {"task": "retrieval", "prompt_name": "document"}

_encoder_cache: dict[str, SentenceTransformer] = {}


def _get_encoder(model_name: str = DEFAULT_MODEL) -> "SentenceTransformer":
    """Lazy-load the SentenceTransformer model with quiet logging."""
    if model_name in _encoder_cache:
        return _encoder_cache[model_name]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

        from sentence_transformers import SentenceTransformer as ST

        encoder = ST(model_name, trust_remote_code=True)

    _encoder_cache[model_name] = encoder
    logger.info("Loaded embedding model: %s", model_name)
    return encoder


def encode_texts(
    texts: list[str],
    model_name: str = DEFAULT_MODEL,
    encode_kwargs: dict | None = None,
) -> np.ndarray:
    """Encode a list of texts into embedding vectors.

    Returns an (N, D) float32 numpy array, L2-normalized.
    """
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    encoder = _get_encoder(model_name)
    kwargs = encode_kwargs if encode_kwargs is not None else DEFAULT_ENCODE_KWARGS

    embeddings = encoder.encode(texts, **kwargs)
    embeddings = np.asarray(embeddings, dtype=np.float32)

    # L2 normalize so dot product = cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    embeddings = embeddings / norms

    return embeddings


def _parse_date_to_months(date_str: str) -> float | None:
    """Parse a date string like '2026.03' or '2026' to months since 2000-01.

    Returns None if parsing fails.
    """
    if not date_str or not date_str[0].isdigit():
        return None
    parts = date_str.split(".")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 6  # default mid-year
        return (year - 2000) * 12 + month
    except (ValueError, IndexError):
        return None


def compute_time_decay_weights(
    n: int,
    metadata: list[dict] | None = None,
) -> np.ndarray:
    """Compute time-decay weights for n corpus papers.

    If metadata is provided, uses actual publication dates so newer papers
    get higher weight regardless of corpus ordering.

    Formula (date-based): w_i = exp(-lambda * age_months), normalized.
    Formula (fallback):   w_i = 1 / (1 + log10(i + 1)), normalized.
    """
    if n == 0:
        return np.array([], dtype=np.float64)

    # Try date-based weights if metadata available
    if metadata is not None and len(metadata) == n:
        months = [_parse_date_to_months(p.get("date", "")) for p in metadata]
        valid = [m for m in months if m is not None]

        if len(valid) >= n * 0.5:  # need at least 50% valid dates
            max_month = max(valid)
            # age in months; papers without date get median age
            median_age = np.median([max_month - m for m in valid])
            ages = np.array([
                (max_month - m) if m is not None else median_age
                for m in months
            ])
            # Exponential decay: half-life ~24 months
            decay_lambda = np.log(2) / 24.0
            raw_weights = np.exp(-decay_lambda * ages)
            return raw_weights / raw_weights.sum()

    # Fallback: index-based decay
    indices = np.arange(n)
    raw_weights = 1.0 / (1.0 + np.log10(indices + 1))
    return raw_weights / raw_weights.sum()


def compute_similarity_scores(
    candidate_embeddings: np.ndarray,
    corpus_embeddings: np.ndarray,
) -> np.ndarray:
    """Compute cosine similarity matrix. Both inputs should be L2-normalized.

    Returns shape (n_candidates, n_corpus).
    """
    return candidate_embeddings @ corpus_embeddings.T


def rank_candidates(
    candidates: list[dict],
    candidate_embeddings: np.ndarray,
    corpus_embeddings: np.ndarray,
    top_k: int = 30,
    time_weights: np.ndarray | None = None,
) -> list[dict]:
    """Rank candidates by weighted embedding similarity to corpus.

    score = sum(similarity * time_decay_weight) * 10
    Returns top_k candidates sorted by score desc, with '_embedding_score' added.
    """
    n_corpus = corpus_embeddings.shape[0]

    if n_corpus == 0:
        scored = [
            {**candidate, "_embedding_score": 0.0} for candidate in candidates
        ]
        return scored[:top_k]

    similarity = compute_similarity_scores(candidate_embeddings, corpus_embeddings)

    if time_weights is None:
        time_weights = compute_time_decay_weights(n_corpus)

    # weighted sum: (n_candidates, n_corpus) @ (n_corpus,) -> (n_candidates,)
    scores = (similarity * time_weights[np.newaxis, :]).sum(axis=1) * 10.0

    scored = []
    for i, candidate in enumerate(candidates):
        scored.append({**candidate, "_embedding_score": float(scores[i])})

    scored.sort(key=lambda x: x["_embedding_score"], reverse=True)
    return scored[:top_k]


def save_embeddings(embeddings: np.ndarray, path: Path) -> None:
    """Save embeddings to a .npy file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, embeddings)


def load_embeddings(path: Path) -> np.ndarray | None:
    """Load embeddings from a .npy file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    return np.load(path)


def append_to_corpus(
    new_texts: list[str],
    new_metadata: list[dict],
    embeddings_path: Path,
    metadata_path: Path,
    model_name: str = DEFAULT_MODEL,
) -> tuple[np.ndarray, list[dict]]:
    """Add new papers to the embedding corpus.

    Encodes new texts, PREPENDS to existing (newest first for time decay).
    Returns updated (embeddings, metadata).
    """
    new_embeddings = encode_texts(new_texts, model_name=model_name)

    existing_embeddings = load_embeddings(embeddings_path)
    existing_metadata: list[dict] = []
    if metadata_path.exists():
        with open(metadata_path) as f:
            existing_metadata = json.load(f)

    if existing_embeddings is not None and existing_embeddings.size > 0:
        combined_embeddings = np.concatenate(
            [new_embeddings, existing_embeddings], axis=0
        )
    else:
        combined_embeddings = new_embeddings

    combined_metadata = new_metadata + existing_metadata

    save_embeddings(combined_embeddings, embeddings_path)
    with open(metadata_path, "w") as f:
        json.dump(combined_metadata, f, ensure_ascii=False, indent=2)

    logger.info(
        "Corpus updated: %d new + %d existing = %d total",
        len(new_texts),
        len(existing_metadata),
        len(combined_metadata),
    )
    return combined_embeddings, combined_metadata


def load_corpus(corpus_dir: Path) -> tuple[np.ndarray | None, list[dict]]:
    """Load corpus embeddings and metadata from a directory.

    Looks for corpus_embeddings.npy and corpus_metadata.json.
    """
    embeddings_path = corpus_dir / "corpus_embeddings.npy"
    metadata_path = corpus_dir / "corpus_metadata.json"

    embeddings = load_embeddings(embeddings_path)

    metadata: list[dict] = []
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)

    return embeddings, metadata


def bootstrap_corpus(
    papers: list[dict],
    corpus_dir: Path,
    model_name: str = DEFAULT_MODEL,
    text_builder=None,
) -> tuple[np.ndarray, list[dict]]:
    """One-time: encode all papers and save as initial corpus.

    text_builder defaults to: lambda p: f"{p.get('title','')}. {p.get('abstract','')}"
    """
    if text_builder is None:
        text_builder = lambda p: f"{p.get('title', '')}. {p.get('abstract', '')}"

    texts = [text_builder(p) for p in papers]
    embeddings = encode_texts(texts, model_name=model_name)

    corpus_dir.mkdir(parents=True, exist_ok=True)
    embeddings_path = corpus_dir / "corpus_embeddings.npy"
    metadata_path = corpus_dir / "corpus_metadata.json"

    save_embeddings(embeddings, embeddings_path)
    with open(metadata_path, "w") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    logger.info("Bootstrapped corpus with %d papers", len(papers))
    return embeddings, papers
