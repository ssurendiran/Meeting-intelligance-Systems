"""
Shared sparse (keyword) encoding for hybrid search: tokenize + hash to indices/values.
Used by indexer (doc) and retriever (query) so dense + sparse use the same dimension.
"""
import re
import math
from collections import Counter
from typing import List, Tuple

SPARSE_DIM = 2**18  # 262144; same for doc and query


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase word tokens (alphanumeric boundaries). Used by text_to_sparse_indices_values."""
    return re.findall(r"\b\w+\b", (text or "").lower())


def text_to_sparse_indices_values(text: str, mode: str = "doc") -> Tuple[List[int], List[float]]:
    """Produce sparse vector (indices, values) for a document or query. mode "doc": values = 1 + log(tf), aggregated by index. mode "query": values = 1.0 per unique token.
    Why available: Shared by indexer (doc) and retriever (query) so hybrid search uses the same sparse dimension and encoding."""
    tokens = _tokenize(text)
    if not tokens:
        return [], []

    if mode == "query":
        seen: set[int] = set()
        indices: List[int] = []
        values: List[float] = []
        for t in tokens:
            idx = hash(t) % SPARSE_DIM
            if idx not in seen:
                seen.add(idx)
                indices.append(idx)
                values.append(1.0)
        return indices, values

    # doc: aggregate by index, value = 1 + log(tf)
    counter: Counter[int] = Counter()
    for t in tokens:
        counter[hash(t) % SPARSE_DIM] += 1
    indices = []
    values = []
    for idx, tf in sorted(counter.items()):
        indices.append(idx)
        values.append(1.0 + (0.0 if tf <= 1 else math.log(tf)))
    return indices, values
