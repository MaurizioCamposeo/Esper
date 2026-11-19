"""Compute embeddings with a sentence-transformers model, loaded once."""

import numpy as np
from sentence_transformers import SentenceTransformer

from esper.config import EMBEDDING_BATCH_SIZE, EMBEDDING_MODEL

class Embedder:
    """An embedding model loaded in memory, with its tokenizer."""
    def __init__(self, model_name: str = EMBEDDING_MODEL, batch_size: int = EMBEDDING_BATCH_SIZE, *, revision: str | None = None) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.revision = revision
        options = {"revision": revision} if revision is not None else {}
        self.model = SentenceTransformer(model_name, device="cpu", **options)
        self.dimensions = self.model.get_embedding_dimension()

    def count_tokens(self, text: str) -> int:
        """Return the number of model tokens in text, without the special tokens."""
        return len(self.model.tokenizer.encode(text, add_special_tokens = False))

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return one normalized float32 vector per text, shape (len(texts), dimensions)."""
        if not texts:
            return np.empty((0, self.dimensions), dtype = np.float32)
        return self.model.encode(texts, batch_size = self.batch_size, normalize_embeddings = True)

    def embed_query(self, query: str) -> np.ndarray:
        """Encode a search description; keep query handling separate from documents."""
        if not query.strip():
            raise ValueError("Search query must not be empty")
        special_tokens = self.model.tokenizer.num_special_tokens_to_add(pair=False)
        if self.count_tokens(query) + special_tokens > self.model.max_seq_length:
            raise ValueError("Search query exceeds the embedding model's token limit")
        # bge-m3 uses the same encoding for queries and documents. Future model
        # adapters can apply their query instruction here without changing search.
        return np.asarray(self.embed([query])[0], dtype=np.float32)

