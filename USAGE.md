# Using Esper

Esper is a local personal archive with a native Qt desktop application and a CLI.
Unless shown otherwise, run commands from the project root.

| Available now | Coming next |
|---|---|
| Native desktop: import, index, search, read passages, manage tags and delete files | OCR for scanned PDFs |
| Digital PDF extraction, page references and native page previews | Complex-layout extraction improvements |
| JPEG/PNG search using OCR and detailed descriptions | Direct image embeddings |
| CLI, full reindexing, hybrid search and versioned benchmarks | Standalone installers |

The CLI now implements **phase 3 search** of `docs/ARCHITETTURA.tex`: semantic
retrieval, keyword retrieval, hybrid ranking, tag filters and source passages.
An evaluation fixture and recall measurement tool are included. Retrieval quality
on a representative real archive still needs its own labelled evaluation.
The desktop connects directly to the same archive and Python functions.

## Requirements

- Linux or macOS
- [uv](https://docs.astral.sh/uv/), the Python package manager. It also downloads the right Python version (3.12) by itself.
- A graphical desktop session to use the native application. Qt/PySide6
  Essentials is installed by uv. Node.js and npm are not used.

Esper runs on the CPU: no GPU is needed.

## Installation

```bash
git clone https://github.com/Maurizio19hub/Esper.git
cd Esper
uv sync
```

`uv sync` creates the virtual environment in `.venv/`, installs the dependencies (PyTorch is the CPU-only build) and installs the `esper` command.

Python and CLI commands are run through `uv run`, which uses the project environment without activating it:

```bash
uv run esper --help
```

## Where your data lives

Your persistent document archive lives in the `data/` folder of the project, which is never committed to git:

| Path | Content |
|---|---|
| `data/esper.db` | SQLite database: documents, tags, chunks, keyword index and embedding vectors |
| `data/files/` | A copy of every imported file, named after the SHA-256 of its content |
| `data/desktop.ini` | Desktop theme, motion, sorting, view and window preferences |

The database is created automatically on the first archive command; `data/files/`
is created on the first successful import. Importing a file **copies** it: the
original stays where it is, and you can move or delete it afterwards. Downloaded
models use a separate Hugging Face cache, described below.

## First run with your own text documents

```bash
uv run esper import "/path/to/notes.md" "/path/to/contract.txt"
uv run esper index
uv run esper list
uv run esper search "il documento con le spese per il riscaldamento"
```

Successfully processed documents appear as `indexed` and can be searched from
the CLI or desktop. Both use this same local archive.

## PDF documents

Digital PDFs follow the same import/index/search workflow as text files.
PyMuPDF extracts each page separately, joins words hyphenated at line breaks,
and removes identical header/footer blocks contained within the outer 50-point
margins when repeated on at least three pages and at least half of the document.
This is a conservative heuristic; complex columns, tables, unusual fonts and
reading order can still need better extraction. Lowercase word fragments joined
across a line-ending hyphen are a heuristic: a genuine hyphenated compound split
at the same point can lose its hyphen. Inline hyphens and uppercase/numeric
identifiers are preserved by the additional cleanup. It is not OCR.

Chunks and overlap never cross a PDF page boundary. Search passages carry
physical page numbers starting at 1. The desktop renders the original PDF at the
first matching passage's page; the page selector and arrow buttons navigate.
Printed page labels may differ from physical positions.

Password-protected PDFs require an unlocked copy. A PDF with no extractable text
gets an explicit error explaining the OCR requirement. A mixed PDF indexes its
readable pages and records a partial-search warning, visible on cards, in the
reader and on CLI indexing stderr. Blank pages also trigger this warning because
the extractor does not infer whether they were intentionally blank or scanned.

Existing databases gain nullable page metadata automatically; TXT/Markdown
indexes remain usable. For a PDF previously marked as an unsupported-format
error, open it and choose **Riprova indicizzazione**, or explicitly rebuild the
archive. Existing errors are not automatically retried at every startup.

## JPEG and PNG images

The regular launch command `uv run esper desktop` uses the image runtime
provisioned in `.esper-runtime/` when present. Esper starts its copy of
Tesseract with the Italian and English language data from that directory and
loads the pinned Florence-2 model from there. The runtime is shared by the CLI and
desktop and is independent of the selected archive.

For a checkout without the provisioned runtime, Esper can use Tesseract on
`PATH` and Florence-2 in the Hugging Face cache. On Fedora, the OCR packages are
`tesseract`, `tesseract-langpack-ita` and `tesseract-langpack-eng`. Use
`tesseract --list-langs` to check the installed languages.
For detailed descriptions, cache the pinned model once (about 470 MB):

```bash
uv run hf download florence-community/Florence-2-base-ft \
  --revision 0b03b6f15a4a211370fb204aee4e7dd48887ea37 \
  --include '*.json' --include '*.txt' --include '*.safetensors'
```

Both engines run locally on every JPEG and PNG. Tesseract reads usable text
and Florence-2 generates an English paragraph describing the scene. Each source
has its own searchable passages: **Testo OCR** and **Descrizione generata**.
CLI JSON exposes the source as `ocr` or `caption`. Italian semantic queries can
retrieve English descriptions through bge-m3. Captions can miss or misidentify
details; open the image to check them.

Previously indexed JPEG and PNG files are queued once when an older archive
is opened. Desktop processes the queue at startup; CLI users can run
`uv run esper index`. If an engine fails and the other produces usable text,
its passages remain searchable with a warning. Open the reader and select
**Riprova indicizzazione** to retry. An unreadable image or two empty/failed
results produce an indexing error. PDF extraction follows the rules above.

## Reproducible benchmarks

See [evaluation/BENCHMARK.md](evaluation/BENCHMARK.md) for the fixed text/PDF
datasets, saved bge-m3 measurements, metric definitions and future model adapter
boundary. Run the complete text benchmark without touching your archive:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run python scripts/benchmark.py run \
  --output /tmp/esper-bge-text.json
```

Results are development measurements, not a guarantee for personal documents.
Use a new output filename for each run; previous reports are never overwritten.

## Commands

### `import`: add files to the archive

```bash
uv run esper import notes.md contract.txt
```
```
imported #1 notes.md
imported #2 contract.txt
```

- Accepts one or more files.
- **Duplicates are detected by content, not by name.** Importing the same content again, even under a different name, does not create a second copy:
  ```
  already present as #1 notes-copy.md
  ```
- A path that is not a file is reported as an error, and the other files are imported anyway.

### `index`: process queued documents

Importing stores files immediately with status `queued`. Run indexing separately:

```bash
uv run esper index
```
```
indexing 2 documents...
indexed 2 documents
```

- Processes all queued documents, one at a time, with one loaded embedding model.
- Supports TXT, Markdown, digital PDFs, JPEG and PNG.
  Extracts their text, splits it into chunks, computes embeddings, and stores
  the chunks with their keyword-index entries and vectors. Successful documents
  become `indexed`.
- The first run downloads bge-m3 if it is not already cached (about 2.3 GB).
  Later runs can use the cached model offline. Embedding runs on the CPU.
- Already indexed documents are skipped. If there is no pending work, prints
  `no documents to index` and exits successfully without loading the model.
- After an interrupted run, documents left in `processing` are put back in the
  queue on the next run. Completed documents are skipped.
- If a document fails, its status becomes `error`, the reason is saved and
  printed on standard error, and processing continues with the next document.
  Unsupported formats can still be stored in the archive. Password-protected,
  damaged and textless PDFs receive explicit processing errors.
- Returns exit code `1` if any document in this run failed, or if the embedding
  model could not load. A model-loading failure leaves document statuses unchanged.
- Documents already in `error` are skipped; use `reindex` to retry every document.
- Before processing pending documents, checks the loaded model, vector dimensions,
  chunk size, overlap and chunker version against the recorded index settings.
  An incompatible index, or an existing index with unknown settings, is rejected
  with instructions to run `esper reindex`. Document states and existing search
  data are preserved when this check fails.
- Ctrl+C returns exit code `130`. Use `esper index` to resume unfinished work.

Indexing prepares the data used by `esper search`.

Current settings in `esper/config.py` are `BAAI/bge-m3` on CPU, batches of 8,
1024-dimensional vectors, a maximum chunk size of 400 model tokens, and up to 50
tokens of overlap. Settings are recorded in the database's `index_settings` row.
The model name and dimensions come from the loaded embedder. Batch size is an
execution setting and is not part of the index identity.

An unbroken word exceeding the budget is split at Unicode character boundaries;
each piece is measured using the model tokenizer. If even a single character
exceeds the chosen budget, processing fails explicitly rather than storing an
oversized chunk. Chunker version 2 records this corrected behavior.

### `reindex`: rebuild all search data

```bash
uv run esper reindex
```
```
reindexing 2 documents...
indexed 2 documents
```

- Reprocesses every archived document, including those already `indexed` or in
  `error`. Original archived files, document IDs, names, timestamps and tags are
  preserved. This command does not import modified files from their old source paths.
- Loads and validates the model before resetting the index. A loading failure
  leaves the previous index intact. A failure during the reset transaction rolls
  the reset back, including the previous vector table and settings.
- The reset clears chunks, full-text entries and vectors, recreates the vector
  table with the loaded model's dimensions, records the new settings, and queues
  all documents in one transaction. Documents are then processed and committed
  individually. The previous search index is replaced at reset time; it is not
  retained as a fallback while documents are rebuilt.
- After Ctrl+C or a process interruption, run `esper index` to continue the queue
  without repeating completed documents. Running `esper reindex` again starts a
  new rebuild from the beginning. Documents that failed are skipped during resume;
  another full rebuild retries them.
- Returns `1` for model, reset or document failures and `130` for Ctrl+C.
  An empty archive prints `no documents to reindex` without loading the model.

**For an archive created before settings tracking, run `uv run esper reindex`
before adding more documents to its index.** Old indexes are never automatically
labelled with today's configuration. Existing settings rows receive a legacy
chunker version during schema migration and require a rebuild too.

After changing the model or chunking configuration, rebuild with this command.
`EMBEDDING_DIMENSIONS` controls the initial table width; reindexing derives the
new table width from the loaded model. Model-specific loading and prompts for
future models such as EmbeddingGemma 2 still need their own integration.

### `search`: find documents from a description

```bash
uv run esper search "la ricevuta della sostituzione della caldaia"
uv run esper search "le spese per la casa" --tag casa --tag ricevute --limit 10
uv run esper search "caldaia" --mode semantic
uv run esper search "caldaia" --mode keyword
uv run esper search "caldaia" --json
```

- The default `hybrid` mode combines exact cosine retrieval over stored vectors
  with FTS5 keyword retrieval ranked by BM25. Only the description is embedded;
  document vectors are reused. The loaded model and index settings must match.
- `--mode semantic` searches by meaning alone. `--mode keyword` uses only FTS5
  and does not import or load the embedding model. Keyword-only search can read
  an index with unknown embedding settings because it does not compare vectors.
- Repeated `--tag` options require **all** named tags. Names are normalized like
  the tag command. Filters apply before ranking limits in both branches.
- Returns up to `--limit` distinct documents (default 5), each with up to three
  source passages and its filename, ID and tags. Only documents with status
  `indexed` and stored chunks are eligible. Queued, processing and errored
  documents are excluded. PDF passages include physical page numbers, starting
  at 1; TXT/Markdown passages have `page: null` in JSON.
- Each passage reports `semantic`, `keyword` or `both`, describing the retrieval
  branches that contributed it. Text output displays up to 240 characters per
  passage; `--json` contains full passage text and metadata using snake_case fields.
  These are core data fields, separate from native widget state.
- The fused score is `sum(1 / (60 + rank))` across branches. A document uses its
  strongest passage's score, so extra chunks do not add votes to its document
  score. The candidate pool starts at 50 per branch and grows if necessary to
  find enough distinct documents. Ties have a stable chunk-ID order.
- These scores order results; they are **not probabilities of relevance**.
  Semantic search returns nearest available passages even for an unrelated
  description. There is no calibrated minimum similarity threshold yet.
- Natural-language keyword input is split into literal words joined by OR.
  Quotes, parentheses and operator-like words are not interpreted as FTS query
  syntax. The tokenizer ignores case and accents; there is no Italian stemming
  or automatic word-prefix expansion.
- Search reads a consistent database snapshot and does not write index data or
  change document states. It checks compatibility again after query inference
  in case the index changed during model work.
- No eligible chunks or unknown tags produce `no results` (or `[]` with
  `--json`) without loading a model. Zero results is exit code 0. Invalid input,
  incompatible settings and loading/inference/database failures return 1;
  Ctrl+C returns 130. Descriptions exceeding the model's context fail explicitly
  rather than being silently truncated.

For an older archive, run `uv run esper reindex` once if search reports unknown
or changed index settings. No server or browser is needed for CLI search.

### `list`: show the archive

```bash
uv run esper list
```
```
#   1 notes.md                            1.2 KiB queued      [home, work]
#   2 contract.txt                          833 B queued
```

The columns are the document number, the original name, the size, the processing status and the tags.

The status is one of:

| Status | Meaning |
|---|---|
| `queued` | imported, waiting to be indexed |
| `processing` | being indexed |
| `indexed` | processed; chunks and search indexes stored |
| `error` | indexing failed |

Documents stay `queued` until you run `uv run esper index`.

To show only the documents that have **all** the given tags, filter with `--tag`. The option can be repeated:

```bash
uv run esper list --tag work
uv run esper list --tag work --tag home
```

### `tag` / `untag`: organize with tags

```bash
uv run esper tag 1 work "house contract"
```
```
#1 [house-contract, work]
```
```bash
uv run esper untag 1 work
```
```
#1 [house-contract]
```

- The first argument is the document number shown by `list`, followed by one or more tags.
- **Tag names are normalized**: lowercase, with spaces replaced by hyphens. `Work`, `WORK` and `work` are the same tag, and `"house contract"` becomes `house-contract`. Use quotes for tags with spaces.
- After every change the command prints the current tags of the document.
- Removing a tag the document does not have is not an error.
- A tag that no document uses anymore is deleted automatically.

### `delete`: remove documents

```bash
uv run esper delete 2
```
```
delete document #2 [contract.txt]? [y/N] y
deleted document #2 [contract.txt]
```

- This removes the database entry, its chunks and search-index entries, the tags that are no longer used and the copy in `data/files/`. **It cannot be undone**, but the original file you imported from is not touched.
- The default answer is **no**: anything other than `y`, including just pressing Enter, skips the document.
- Add `-y` (or `--yes`) to skip the confirmation, for example in scripts:
  ```bash
  uv run esper delete 2 3 -y
  ```
- Document numbers can be reused: after deleting the document with the highest number, the next import gets that number again. Always check with `list` before deleting.

### Exit codes

Every command follows the usual convention, so it can be used in scripts (`esper import x.md && echo done`):

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | at least one operation failed (missing file, unknown document, empty tag name…) |
| `2` | wrong command line (unknown command, missing argument, a document number that is not a number) |

Error messages are printed on standard error, so `uv run esper list > archive.txt` writes only the list to the file.

## Native desktop application

From the project root:

```bash
uv run esper desktop
```

This opens a native Qt window. The former Svelte interface, demo data, frontend
build and HTTP client have been removed. No server or browser is launched.

To keep a separate archive for experiments:

```bash
uv run esper desktop --data-dir /path/to/separate/archive
```

- Start a natural-language query or choose one of the example queries.
- Use **Tutti i documenti** to browse the archive, switch between grid and list,
  sort files, or combine file-type and tag filters.
- The recall viewer shows actual archive images or passages. Use its arrows to
  select another document, then click to open it.
- Add documents with the plus button or drag and drop. They are copied to the
  real archive and indexed in the background. Pending/interrupted documents are
  recovered on launch; the **Indicizza in attesa** button also resumes the queue.
- Search is real bge-m3/FTS5 retrieval. Beside **Cerca per**, select **Entrambi** for hybrid search, **Significato** for semantic search or **Parole chiave** for keyword search. Tag filters combine in AND.
- Open a card for native TXT/Markdown previews, full source passages, metadata,
  tag editing, original-file opening and confirmed deletion. The preview reads
  the original rather than joining overlapping chunks. Large text previews are
  limited to 2 MB; the archived original remains complete.
- Images have native previews. Digital PDFs are searchable and render natively
  on the matching result's page. Use the page selector or arrows to navigate;
  **Apri originale** still opens the archived PDF in the system reader.
  Mixed PDFs show a partial-search warning listing pages without extractable
  text. JPEG and PNG use the OCR and image-description workflow described above.
- **Ricostruisci indice** rebuilds search data after confirmation, including
  documents in error. Use it when an old index has unknown/incompatible settings.
  Originals, document metadata and tags are preserved; derived indexes are reset.
- The theme button switches dark/light; pause stops optical motion. Theme,
  motion, sorting, grid/list view, search mode and window geometry are stored in
  `desktop.ini` in the selected archive. Qt's system reduced-motion hint is
  respected on platforms exposing it.
- `/`, **Ctrl+K** or **Cmd+K** focuses search. **Esc** clears search or closes the
  document dialog. **F5** refreshes the archive. In the recall viewer, left/right
  selects a frame and Enter opens it.
- Model loading, indexing and search use one background worker and reuse one
  loaded model. Each operation opens its own database connection. Old queued
  queries are skipped; late results cannot overwrite a newer description.
- Closing lets the current operation finish and stops between documents.
  Completed work is retained; unfinished indexing resumes on the next launch.

The app starts with your archive, without seeded demo documents. The first model
use may download bge-m3 if absent from the Hugging Face cache; cached models can
run offline. See [DESIGN.md](DESIGN.md) for the design and implementation boundary.
Source launch through uv is supported; standalone release installers are future work.

### Exploring the 3D archive

Open **Mappa 3D** in the sidebar. Each positioned file has a marker. Images use
squares, PDFs use diamonds, and notes and texts use circles. Drag to rotate,
scroll to zoom and use **Centra** to restore the initial view. With the map
focused, arrow keys rotate, plus/minus zoom and Home resets the camera.
Click a marker or choose a filename below the map to inspect its links. The
selector also reaches overlapping markers and files waiting for indexing.
Double-click a marker or select **Apri documento** to read the file.

Esper averages each file's existing passage vectors, including OCR and visual
descriptions, and normalizes the result. It projects these document vectors
onto three principal axes. This compresses many dimensions, so positions only
approximate semantic distances. Each file proposes up to four nearest neighbors
whose original cosine distance is below **0.30**. A line is shown if either
endpoint proposes the other. The inspector reports the closest linked file and
its cosine distance. The cutoff controls the map's link density and has no effect
on search rankings.

SQLite saves coordinates and links on first opening the map. Revisiting an
unchanged archive reuses that layout across app restarts. When indexed content
changes, the next map refresh fits the archive again, so existing points can
move. Files without a usable embedding remain accessible in the selector with
their indexing status.

## Starting over

To empty the archive completely, delete the whole data folder:

```bash
rm -rf data/
```

The next command creates an empty database. Always delete the database **and** the files together: deleting only one of them leaves the other out of sync.

## For developers

Run the test suite (it never touches `data/`):

```bash
uv run pytest
```

Measure retrieval on the fictional corpus (20 documents, 40 labelled queries):

```bash
uv run python scripts/evaluate_search.py --mode all
uv run python scripts/evaluate_search.py --mode hybrid --json
```

This builds a temporary archive and reuses one model. It never reads or changes
`data/`. Supply another corpus with `--dataset /path/to/dataset.json`.
[evaluation/README.md](evaluation/README.md) documents the format, metrics and
initial offline results. The development fixture achieved recall@5 and recall@10
of 1.0 for hybrid and semantic modes; that is not a quality guarantee for personal
documents or a performance measurement on large archives.

Check the environment:

```bash
uv run python scripts/check_sqlite.py     # SQLite version and the sqlite-vec extension
uv run python scripts/test_embedding.py   # loads the embedding model (bge-m3) and compares three sentences
```

`test_embedding.py` downloads the model the first time it runs, about 2.3 GB. After that the model is cached in `~/.cache/huggingface/` and Esper works offline.

Inspect how a text document is split, without importing it or writing to the archive:

```bash
uv run python scripts/show_chunks.py notes.md
uv run python scripts/show_chunks.py notes.md --max-tokens 250 --overlap 30
```

This tool loads the model to use its tokenizer and prints each chunk with token
counts. Its options affect that inspection only; they do not change `config.py`.

Run only the native UI checks without opening a visible window:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_desktop.py tests/test_desktop_service.py
```

The full suite also uses Qt's offscreen platform for desktop tests. Tests use
temporary archives and preferences, never the real `data/` directory.
