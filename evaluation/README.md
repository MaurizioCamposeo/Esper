# Retrieval evaluation

For the expanded versioned benchmark (text and real PDF assets), runtime/memory
measurements and model comparisons, use **[BENCHMARK.md](BENCHMARK.md)**.
The original 20-document demo and its runner below remain available unchanged.

`demo.json` contains a fictional Italian archive of **20 documents and 40 labelled
queries**. Topics include paired documents that can be confused, such as boiler
installation/maintenance, electricity/gas bills and apartment/garage contracts.
One query has two relevant documents; two queries include AND tag filters.
None of the documents describe the user's real archive.

Run from the project root:

```bash
uv run python scripts/evaluate_search.py --mode all
uv run python scripts/evaluate_search.py --mode hybrid --json
```

The script loads one bge-m3 model, creates a temporary database and archive,
imports/indexes the supplied documents and evaluates each mode. Temporary files
are removed afterwards; `data/` is never read or modified. The model is downloaded
through its normal cache if absent. To require cached files and disable network
access for model loading:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run python scripts/evaluate_search.py --mode all
```

The JSON report includes the expected and retrieved document IDs for every query.
IDs correspond to documents in dataset order, starting at 1.

## Metrics

Recall@k is the fraction of a query's relevant documents present in its first k
distinct document results. The report averages this fraction across queries.
For a query with two relevant documents, finding one at rank 1 gives recall@1 of
0.5. Retrieving nothing gives zero. These scores are not relevance probabilities.

The first offline run on **2026-11-13**, with bge-m3 on CPU and 400/50-token chunks:

| Mode | Recall@1 | Recall@5 | Recall@10 |
|---|---:|---:|---:|
| Hybrid | 0.9875 | 1.0000 | 1.0000 |
| Semantic | 0.9875 | 1.0000 | 1.0000 |
| Keyword | 0.9375 | 0.9750 | 1.0000 |

All single-document labels were first in hybrid and semantic mode. The two
energy bills occupied the first two positions for their shared query.
Keyword retrieval missed the dental receipt in the first five results for the
paraphrase “Quanto ho speso per farmi curare i denti?”.

This is a small, fixed development fixture written with its labels. It checks
that the retrieval pipeline works; it is **not an independent benchmark**, a
large-archive performance test or evidence of the same recall on a real archive.
No ranking parameters were tuned on this run. Quality on personal documents
still needs representative, separately labelled queries.

## Supply another corpus

```bash
uv run python scripts/evaluate_search.py --dataset /path/to/dataset.json --mode all
```

Use this shape:

```json
{
  "documents": [
    {"key": "bill", "text": "A document's complete text.", "tags": ["home"]}
  ],
  "queries": [
    {"query": "A natural-language description", "relevant_documents": ["bill"], "tags": ["home"]}
  ]
}
```

Document keys and contents must be unique. Each query needs at least one known
relevant key, and its tag filters must include every labelled relevant document.
The script validates these constraints before loading the model.

Implementation references: [sqlite-vec exact distance queries](https://alexgarcia.xyz/sqlite-vec/features/knn.html#manually-with-sql-scalar-functions)
and [SQLite FTS5/BM25](https://www.sqlite.org/fts5.html#the_bm25_function).
