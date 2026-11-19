"""Check query handling through a lightweight model stand-in in a fresh process."""

import subprocess
import sys


def test_query_embedding_checks_context_and_returns_float32_without_truncation():
    script = r'''
import sys
from types import ModuleType
import numpy as np

class Tokenizer:
    def encode(self, text, add_special_tokens=False):
        return list(range(len(text)))
    def num_special_tokens_to_add(self, pair=False):
        return 2

class Model:
    def __init__(self, model_name, device):
        self.tokenizer = Tokenizer()
        self.max_seq_length = 6
        self.calls = []
    def get_embedding_dimension(self):
        return 3
    def encode(self, texts, batch_size, normalize_embeddings):
        self.calls.append(texts)
        assert normalize_embeddings
        return np.array([[0.6, 0.8, 0.0] for _ in texts], dtype=np.float64)

module = ModuleType('sentence_transformers')
module.SentenceTransformer = Model
sys.modules['sentence_transformers'] = module
from esper.embedding import Embedder
embedder = Embedder('test/model')
result = embedder.embed_query('cats')
assert result.shape == (3,)
assert result.dtype == np.float32
assert np.isclose(np.linalg.norm(result), 1)
for query in ('', '   ', 'longer'):
    try:
        embedder.embed_query(query)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid query was encoded')
assert embedder.model.calls == [['cats']]
assert 'torch' not in sys.modules
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
