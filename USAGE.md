# Using Esper

Esper is still a work in progress. This page covers the working command-line archive and the web interface preview. Unless shown otherwise, run commands from the project root.

| Available now | Coming next |
|---|---|
| Import, list, tag and delete files; index text and Markdown documents | Full reindexing, then hybrid search with `esper search "..."` |
| Preview the redesigned web interface with demo documents | FastAPI backend and connection to the real archive |

The backend is at **phase 2, step 6** of `docs/ARCHITETTURA.tex`. Full reindexing
and recording the settings used to build the index remain unfinished in step 7,
which has been deferred while working on the interface. Real natural-language
search is phase 3; connecting it to the browser is phase 4.

## Requirements

- Linux or macOS
- [uv](https://docs.astral.sh/uv/), the Python package manager. It also downloads the right Python version (3.12) by itself.
- For the web preview only: Node.js and npm. The installed Vite version requires
  Node.js `^20.19.0` or `>=22.12.0`.

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

The database is created automatically on the first archive command; `data/files/`
is created on the first successful import. Importing a file **copies** it: the
original stays where it is, and you can move or delete it afterwards. Downloaded
models use a separate Hugging Face cache, described below.

## First run with your own text documents

```bash
uv run esper import "/path/to/notes.md" "/path/to/contract.txt"
uv run esper index
uv run esper list
```

Successfully processed documents appear as `indexed`. This verifies ingestion
and prepares the search data; there is no real search command yet. The web
preview described below uses a separate demo archive.

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
- Supports `.txt` and `.md` files identified as `text/plain` or `text/markdown`.
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
  Unsupported files such as PDFs currently fail at text extraction; they can
  still be stored in the archive.
- Returns exit code `1` if any document in this run failed, or if the embedding
  model could not load. A model-loading failure leaves document statuses unchanged.
- Documents already in `error` are skipped; this command does not retry them.
  A full reindexing command is planned next.

Indexing prepares the search data; the search command is not implemented yet.

Current settings in `esper/config.py` are `BAAI/bge-m3` on CPU, batches of 8,
1024-dimensional vectors, a target chunk size of 400 model tokens, and up to 50
tokens of overlap. Editing these settings does not rebuild existing documents;
index-settings tracking and full reindexing are still pending.

Known limitation: a single unbroken word longer than the token target is currently
kept whole, so the chunker does not enforce a strict 400-token cap in that case.
This implementation gap is also recorded in the architecture guide.

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

## Web interface preview

From the project root:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**, or the Local URL printed by Vite if that port is
already in use. Stop the development server with **Ctrl+C**. `npm install` is
needed on first setup or when dependencies change.

- Start a natural-language query or choose one of the example queries.
- Use **Tutti i documenti** to browse the archive, switch between grid and list,
  sort files, or combine file-type and tag filters.
- Select an image in the recall viewer, then open it to inspect the document.
  Document details include previews, source passages, metadata, editable tags,
  and deletion with confirmation. An original-file link appears when available.
- Add documents with the plus button or drag and drop. In this preview, their
  processing and search behavior are simulated.
- The sun/moon button changes the monochrome theme; the pause button stops the
  animations. Theme, motion, view, and sort preferences are remembered in the
  browser. The system's reduced-motion preference is respected too.
- `/`, **Ctrl+K**, or **Cmd+K** focuses search. **Esc** closes the document viewer
  or mobile menu. Arrow keys switch between the viewer's tabs.
- A URL such as `http://localhost:5173/?q=contratto` preloads a query.

**The preview uses in-memory demo documents, separate from `data/esper.db`.**
Reloading restores the sample archive and discards uploaded demo documents,
tag edits, and deletions; the appearance preferences remain saved. Demo PDF,
OCR, and image searches do not represent implemented backend capabilities.

The HTTP client is prepared for phase 4, but there is no FastAPI server yet.
Leave `VITE_API` unset for this preview; setting it to `http` does not start or
implement the backend. See [frontend/README.md](frontend/README.md) for the
component structure and [frontend/DESIGN.md](frontend/DESIGN.md) for the visual
direction and generated demonstration image.

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

Check or build the frontend from the project root:

```bash
npm --prefix frontend run check
npm --prefix frontend run build
```

The production frontend build is written to `frontend/dist/`.
