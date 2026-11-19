# bge-m3 baseline — 2026-11-14

**Scope:** fixed fictional development datasets, measured offline on the local CPU. These scores do not estimate accuracy on an unseen personal archive. No retrieval tuning was performed.

CPU: 11th Gen Intel(R) Core(TM) i7-1195G7 @ 2.90GHz; PyTorch threads: 4. Model: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, 1024 dimensions, 400/50-token chunks, chunker version 2.

## Text: 45 documents, 85 queries

82 answerable queries contribute to quality averages. Three unanswerable queries are measured separately. Each query has three timed repetitions after a warm-up.

| Mode | Hit@1 | Recall@5 | MRR@10 | nDCG@10 | Median | p95 |
|---|---:|---:|---:|---:|---:|---:|
| hybrid | 84.1% | 93.9% | 0.8876 | 0.9088 | 135.0 ms | 210.3 ms |
| semantic | 93.9% | 99.4% | 0.9695 | 0.9754 | 131.8 ms | 225.1 ms |
| keyword | 73.2% | 89.0% | 0.8033 | 0.8256 | 11.0 ms | 16.3 ms |

Build: 7.00 s model load; 19.32 s indexing; 50 chunks. SQLite: 4.18 MiB. Process peak RSS: 2.08 GiB.

Semantic search finds a relevant document first for 77/82 queries and within five for all 82; recall@5 is below 100% because one query has multiple relevant documents. Hybrid ranks a relevant document first for 69/82 queries. Its failures include cross-language queries and confusable documents. The saved rankings suggest the broad keyword branch can weaken a strong semantic ranking; this is a finding to investigate, not a reason to silently retune the benchmark or change the default.

All modes return an empty result for only one of the three unanswerable cases: the deliberately absent tag. Neither unfiltered unanswerable query is rejected. There is no calibrated relevance cutoff.

The pre-PDF and post-PDF text runs have exactly the same recall, hit, MRR and nDCG values in every mode. Timing differences between these single runs are not evidence of a speedup.

## PDF: 10 documents, 23 queries

22 answerable queries, one unanswerable; 29 indexed text pages/chunks. The mixed PDF has an image-only page 2, correctly reported as a partial-search warning.

| Mode | Recall@5 | MRR@10 | First page hit@1 | Page hit@5 | Median |
|---|---:|---:|---:|---:|---:|
| hybrid | 100.0% | 0.9409 | 81.8% | 100.0% | 140.9 ms |
| semantic | 100.0% | 1.0000 | 100.0% | 100.0% | 147.4 ms |
| keyword | 90.9% | 0.8447 | 59.1% | 86.4% | 3.1 ms |

Build: 7.38 s model load; 3.42 s indexing. SQLite: 4.12 MiB. Process peak RSS: 1.94 GiB.

First page hit@1 evaluates the exact page the desktop opens: 22/22 for semantic, 18/22 for hybrid, 13/22 for keyword. Page hit@5 checks any expected page among the returned passages of the first five documents. These are simple synthetic layouts; no OCR, difficult tables or complex columns were benchmarked. All three modes return results for the unanswerable PDF query.

## Artifacts and next comparisons

- [Pinned text report](bge-m3-text-v1-final.json)
- [Pinned PDF report](bge-m3-pdf-v1-final.json)
- [Original pre-PDF text run](bge-m3-text-v1.json)
- [Initial PDF run](bge-m3-pdf-v1.json)
- [Protocol, commands and extension guide](../BENCHMARK.md)

Keep these manifests and labels unchanged when comparing a future Gemma adapter. New PDF/image/audio datasets should have their own versions and matching baselines. A representative separately labelled real-world collection and larger archives remain necessary before generalizing quality or latency.
