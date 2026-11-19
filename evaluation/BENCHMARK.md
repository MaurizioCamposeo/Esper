# Esper retrieval benchmark

This benchmark measures **Esper's full retrieval pipeline with bge-m3**, not the
embedding model in isolation. It imports real files, extracts and chunks them,
builds a fresh SQLite/FTS/vector index, then calls the same search function used
by the CLI and desktop. All archives are temporary; `data/` is never used.

Read the [measured bge-m3 baseline and findings](results/README.md) for the current
results, timings and limitations, or inspect the full JSON reports alongside it.

## Frozen datasets

| Manifest | Documents | Queries | Purpose |
|---|---:|---:|---|
| `benchmark-v1.json` | 45 | 85 | Text ranking and latency; 82 answerable, 3 unanswerable |
| `pdf-v1.json` | 10 | 23 | Digital PDF retrieval and page provenance; 22 answerable, 1 unanswerable |
| `demo.json` | 20 | 40 | Earlier lightweight development check; separate legacy runner |

The text dataset incorporates the original demo plus harder documents and
queries: similar products, reversed identifiers, old/new instructions, negation,
paraphrases, typos, English/Italian retrieval, multiple relevant documents and
AND tag filters. A deliberately repetitive long manual tests chunk grouping.
Query `slices` report these categories separately; they may overlap.

The PDF assets in `assets/pdf-v1/` are fixed, fictional, three-page PDFs created
with PyMuPDF: ordinary text blocks, repeated margin headers/footers, and one
image-only page in a mixed PDF. Labels include the expected physical source page.
They exercise ingestion and provenance, not complex publishing layouts.

Documents and relevance labels were authored together and frozen before their
first benchmark run. This is a **development benchmark, not an independent test
set or a measurement of accuracy on personal documents**. No search weights or
thresholds were tuned to these results. Short corpora cannot predict latency on
thousands of documents. Add separately labelled real-world examples before
making product quality claims.

## Run and compare

From the repository root, with the model already cached:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run python scripts/benchmark.py run \
  --dataset evaluation/benchmark-v1.json --output /tmp/bge-text.json

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run python scripts/benchmark.py run \
  --dataset evaluation/pdf-v1.json --output /tmp/bge-pdf.json

uv run python scripts/benchmark.py compare \
  evaluation/results/bge-m3-text-v1-final.json /tmp/bge-text.json
```

Without the offline environment variables, model loading may download missing
weights. `--mode semantic|hybrid|keyword|all` defaults to all; `--repeats 3`
controls timed repetitions. `--revision HASH` explicitly pins the bge-m3 model.
Otherwise the runner pins the cached config snapshot when available and records
that revision. It refuses to overwrite an existing output file.

Each run builds a new index at the model's actual dimension. The callable
`model_factory` boundary in `esper.benchmark.run_benchmark` accepts a future model
adapter providing `model_name`, `dimensions`, `count_tokens`, `embed` and
`embed_query`. This includes separate document/query prompt handling inside the
adapter. **Gemma is not loaded or implemented by this milestone.** Do not change
only the model name and assume its prompt/loading requirements are satisfied.
The CLI deliberately continues to use the supported bge-m3 adapter.

Comparisons require the same dataset fingerprint and retrieval protocol. Model
and vector dimension changes are allowed because each run has its own index.
Changed chunk settings are flagged as configuration comparisons. Different
hardware, package versions, source code or repetition settings generate warnings
for runtime comparisons. The report lists metric deltas and per-query MRR
regressions; these are descriptive, not statistical significance tests.

## Metrics and timing boundaries

- **Recall@1/5/10:** fraction of all relevant documents found in the first k.
  With two relevant documents, recall@1 can be at most 0.5.
- **Hit@1/5/10:** whether at least one relevant document appears in the first k.
- **MRR@10:** reciprocal rank of the first relevant result, or zero if none is
  in the first ten. Higher means less searching through results.
- **nDCG@1/5/10:** binary relevance discounted by `1 / log2(rank + 1)`, normalized
  by the ideal ranking. Unjudged documents count as irrelevant.
- **Page hit@1/5:** whether an expected page occurs among the returned passages
  of any of the first k documents. Search returns at most three passages per
  document. This is not recall of every relevant page. The denominator is only
  queries with page labels.
- **First page hit@1:** whether the very first passage in the top document is
  on an expected page. This measures the page the desktop opens automatically.
- **Unanswerable empty-result rate:** fraction of no-relevant-document queries
  returning nothing. These queries are excluded from recall/MRR/nDCG averages.
  Semantic/hybrid retrieval currently has no rejection threshold, so unrelated
  nearest neighbours are expected when eligible documents exist. A missing tag
  filter correctly produces an empty result; do not confuse it with semantic
  abstention.
- **Search latency:** wall time for the complete production search call,
  including query encoding, settings checks, SQLite retrieval, fusion, grouping
  and passage reads. One unmeasured warm-up query per mode follows indexing.
  Then each query is repeated three times consecutively, with no added embedding
  cache. Reports include raw samples, median, nearest-rank p95, min/max and
  ranking stability. Mode order is recorded. This is serial warmed-process
  latency, not cold-start or concurrent UI responsiveness.
- **Build:** model load time (including heavy Python imports), file import time,
  indexing time (extraction + chunking + document embeddings + persistence),
  chunks/second and SQLite size after WAL checkpoint. Original asset sizes and
  model cache are not part of database size.
- **Memory:** OS process lifetime peak resident set size. It includes Python,
  model, temporary data and retrieval; it is not model-only memory or incremental
  RAM. Use a fresh process for each run, especially when comparing models.

Timing depends on CPU load, threads, caches and power settings. Keep the machine
otherwise idle and compare multiple independent runs. Repeated queries do not
increase the number of independent relevance judgements.

Reports record environment/packages, CPU and thread count, source hash, Git HEAD
and dirty state, model adapter/revision/dimensions/batch size, chunk settings,
protocol, exact asset hashes, full rankings, labels and per-query timings. The
manifest fingerprint includes content and labels; changing either creates a
different task. The initial `bge-m3-text-v1.json` run predates PDF support and
explicit snapshot pinning (revision is null). Prefer the pinned `*-final.json`
text baseline for future comparisons; retain the original as the pre-PDF record.

## Adding formats and datasets

Create a new manifest/version; keep existing fixtures unchanged. A document has
a stable `key`, `format`, optional tags, and exactly one of inline `text` (TXT/MD)
or a relative `path` to a real file under the manifest directory:

```json
{
  "schema_version": 1,
  "name": "my-pdf-set",
  "version": "1.0",
  "description": "Describe source, provenance and labelling method",
  "documents": [
    {"key": "invoice", "format": "pdf", "path": "assets/invoice.pdf", "tags": ["home"]}
  ],
  "queries": [
    {"id": "cost", "query": "What did the installation cost?",
     "relevant_documents": ["invoice"], "relevant_pages": {"invoice": [2]},
     "tags": ["home"], "slices": ["pdf", "paraphrase"]}
  ]
}
```

Empty `relevant_documents` means explicitly unanswerable, not missing labels.
Tag filters must retain every relevant document. Duplicate content is rejected
because Esper would deduplicate it. Asset paths cannot escape the dataset folder.
Page numbers are one-based physical PDF positions, not printed page labels.

The manifest can carry future image/audio/other assets through the same file
boundary. Their production extractor/retriever must exist before they can run:
unsupported files fail the benchmark rather than silently disappearing. This
milestone evaluates text queries only; image/audio queries and their relevance
metrics will need a versioned protocol extension when those features arrive.

Definitions: [Stanford IR ranking evaluation](https://web.stanford.edu/class/cs224u/2021/slides/CS224U-IR-part-2.pdf).
PDF extraction follows [PyMuPDF text extraction APIs](https://pymupdf.readthedocs.io/en/latest/recipes-text.html).
