# Working together on Esper

## Role and collaboration

On 2026-11-13 the user explicitly changed the collaboration mode: the assistant
now handles application implementation, supporting tests, verification and
documentation because the user has little time. Earlier guide-only checkpoints
below are historical. Keep explaining the purpose of changes and report results.

- Explain the purpose and reasoning behind the next change before presenting
  implementation details. Connect explanations to the actual project code.
- Show how a new function fits into the whole pipeline, including which
  existing function produces its inputs and who will call it. The user has
  explicitly requested pipeline diagrams to connect helpers with chunking.
- Work in understandable, verifiable increments. Implement authorized changes
  directly without waiting for the user to write each function.
- Offer focused examples or code snippets when useful; avoid delivering a whole
  feature at once unless the user asks for it.
- Guidance can include exact code for the current function or step, with an
  explanation of how it works. It can also describe the approach and let the
  user work out the implementation. Adapt to the user's questions; do not turn
  the guide role into withholding useful code or giving only vague hints.
- Read code, investigate problems, preserve existing user work, and implement
  within the authorized scope. The assistant handles application code,
  supporting pytest tests and verification. Use temporary data for tests.
- The user handles commits and pushes.
- Code comments and docstrings must be in English. Respond in the language the
  user is currently using; the earlier Claude conversations were in Italian.
- Explain errors and help the user reason through the fix. Distinguish confirmed
  facts from assumptions and do not claim to remember conversations you cannot
  access.
- The user has authorized creating and maintaining this file for continuity.
  Keep its checkpoint accurate as work progresses, without treating tentative
  suggestions as completed work or settled decisions.

## Project and development approach

Esper is a local personal document archive. Its goal is to find documents from
natural-language descriptions through hybrid semantic and keyword search.

- Follow the incremental roadmap in `docs/ARCHITETTURA.tex`. Each phase needs a
  verifiable working result before moving to the next.
- Build and understand the core through command-line tools first. The API and
  interface integration come later.
- Current tools: Python 3.12, uv, Qt Widgets through PySide6 Essentials, PyMuPDF,
  SQLite with FTS5 and sqlite-vec,
  sentence-transformers, and CPU-only PyTorch. The configured embedding model is
  `BAAI/bge-m3` with 1024 dimensions.
- Original archived files and metadata are the primary data. Chunks and search
  indexes must be regenerable. Do not alter the user's real archive for tests.
- Preserve existing user changes. Inspect the working tree before editing.
- Esper is intended for public release. Favor dependencies and model runtimes
  that can ship through a straightforward desktop install. Release setup must
  install or provision the required local models, OCR engine and language data
  so users can index and search without developer commands or manual model
  downloads. Consider install size and future updates when choosing models and
  dependencies.

## Starting a new chat

1. Read this file and inspect `git status`, recent commits, and the code relevant
   to the user's request.
2. Use `docs/ARCHITETTURA.tex` for the roadmap, `USAGE.md` for desktop/CLI
   behavior, and `DESIGN.md` for native interface design. The former HTTP
   contract and web frontend were removed; the desktop calls Python directly.
   Documentation may lag behind implementation; verify against the code.
3. Briefly establish the current step and resume the agreed workflow from there.
   Use the user's current authorization to determine implementation scope.

## Model delegation — 2026-11-19

- Use Terra 6.1 for visual work such as fixture selection, image inspection,
  screenshot review, and reproducing failures with visual inputs.
- Keep routine implementation and test tasks with the primary agent. The user
  removed Luna from the delegation workflow.
- Give each delegated task a specific deliverable and separate file ownership
  where it involves edits. The primary agent owns integration, migrations and
  verification through the normal entry points.
- Get the user's approval before any use of Astra 6.2, including a model switch
  or delegation. Explain which decision or blocker would benefit from it.

## Native search controls and spatial archive — 2026-11-19

- The desktop uses three always-visible choices for keyword, semantic and hybrid
  search. The compact home keeps the optical preview and recent files visible.
  Map selection, keyboard controls and opening a file use the normal native reader.
- Mappa 3D aggregates existing passage embeddings to one unit vector per file.
  PCA supplies three display coordinates. Each file nominates up to four neighbors
  below cosine distance 0.30. SQLite caches points and edges by archive revision
  and layout version. Opening an older index builds the map without re-embedding.
  Files without a usable vector remain available in the file selector.
- The map refits after indexed membership or vectors change. Positions can move.
  Projection distorts distances, and exact link calculation is quadratic on a cache
  miss. The threshold is a display choice with no effect on search relevance.
- Verified offline on 23 fictional and fixture files using bge-m3, including PDF
  and JPEG. All 23 had coordinates, four links passed the default rule, and a
  reopened archive returned identical geometry. The test suite passed 447 tests.
  Terra checked home, results and the map at 1040×650 and 1440×900 in both themes.

## Detailed descriptions and OCR together — 2026-11-19

- The user approved running OCR and visual description on every standalone JPEG
  and PNG. This supersedes the earlier fallback-only milestone. The captioner
  now uses the native Transformers Florence-2-base-ft model with its paragraph
  caption task on CPU. The pinned weights are provisioned in the project runtime.
- Every usable transcription and description has its own labelled passages in
  the existing bge-m3 and FTS indexes. Partial engine failures retain searchable
  output with a warning and a retry action. Schema version 1 queues previously
  indexed JPEG/PNG files once to regenerate their passages.
- Terra reviewed the Qt layout at 1040×650. The activity strip displays model
  loading, the active filename and pending count independently of result filters.
  Cards show the specific extraction warning. Background polling preserves
  existing cards while the document snapshot is unchanged.
- The full suite passed with 440 tests. Offline checks used a receipt and a
  textless photo, including exact-word and Italian semantic retrieval. These
  examples establish functionality; broader search quality remains unmeasured.
- Refreshed all six existing images in the user's designated test archive.
  All six have captions, three also have usable OCR, and none had a warning.

## JPEG and PNG search — 2026-11-19

- Started phase 6 with standalone JPEG/PNG. `extract_document` runs Tesseract
  with Italian and English data in sparse-text mode, and uses word confidence
  to choose between an OCR transcription and an offline BLIP description.
  OCR engine failures surface as indexing errors. Corrupt images fail before OCR.
- BLIP is pinned to Salesforce revision
  `82a37760796d32b1411fe092ab5d4e227313294b`, loaded lazily on CPU from the
  Hugging Face cache. Descriptions are in English. A single branch supplies
  text to the existing chunking, FTS and bge-m3 indexing path. No embedding
  model or index dimensions changed.
- Chunks persist their source (digital text, OCR or caption). Old rows default
  to digital text. CLI JSON exposes it, and desktop cards and the reader label
  OCR and generated matches. Older failed JPEG/PNG imports can be retried in
  the reader once prerequisites are installed. Archived originals are preserved.
- Terra 6.1 prepared five fixtures and found that the local GLM OCR model echoed
  its prompt on the textless sample, and that Tesseract gave a false two-letter
  token slightly above 70 confidence on the watermarked sample. The OCR
  heuristic now rejects isolated short alphabetic tokens and keeps clear
  identifiers. It can still miss short words or fine print.
- Offline smoke test with actual Tesseract 5.5.3, BLIP and bge-m3 indexed five
  images in a temporary archive. Keyword search found the receipt and
  `AB-7429`; an Italian semantic query ranked the textless tomato photo first.
  The tiny watermark was missed by OCR, which triggered the description path.
  Both OCR languages and the BLIP cache were staged in `/tmp` for verification.
  This was a smoke test on a few fixtures. The real archive was not used.
- Full suite: 432 passing tests, including OCR routing and failures, caption
  provenance, compatibility with existing chunks, and desktop retry.
- Updated README, USAGE, DESIGN and architecture source/PDF. Scanned PDF OCR,
  generating both OCR and captions for the same image, and direct visual
  embeddings remain future work. The user explicitly deferred generating both.

## Image runtime and normal launch — 2026-11-19

- Two fresh imports showed that the temporary launcher was insufficient for
  routine testing. The user approved Astra 6.2, which confirmed that the
  reported error came from the executable lookup and that the normal
  environment lacked both Tesseract and a cached BLIP model.
- This checkout now has an ignored `.esper-runtime/` directory on disk.
  Esper runs its Tesseract binary by absolute path with explicit Italian and
  English language files, and loads the pinned BLIP snapshot from disk.
  System Tesseract and the usual BLIP cache remain valid for other checkouts.
  The existing bge-m3 cache is used through its normal location.
- Verified fresh offscreen desktop imports with no Tesseract on `PATH` and
  the temporary cache and language environment cleared. The real OCR and
  caption paths both worked, including an Italian search. The two PNGs that
  had failed in the user's temporary test archive were retried successfully.
  The full suite passed with 433 tests.
- Launch the same test archive with
  `uv run esper desktop --data-dir /tmp/esper-image-test`.
  The runtime staging is specific to this checkout and Fedora machine.

## Collaboration and delivery update — 2026-11-13

- The user delegated coding and associated development work to the assistant,
  superseding the earlier guide-only workflow. The user then explicitly
  authorized proceeding with the phase 2 completion milestone.
- Phase 2, step 7 and the oversized-word fix are complete; see verification below.
  The starting HEAD was `4cc45d6`; the assistant has not committed or pushed.
- Keep bge-m3 active while designing reusable model settings/loading boundaries
  for future EmbeddingGemma 2 text support. Do not switch models now.
- The user subsequently selected native desktop delivery and removal of the web
  interface. Qt Widgets is now implemented; see the native desktop checkpoint.
  Keep the core independent of widgets and retain the working CLI.

## Phase 2 completion — 2026-11-13

- Implemented saving/validating index settings and compatibility barriers in
  `esper/index_settings.py`, integrated into both direct document indexing and
  queued processing. Metadata records the loaded model name, actual output
  dimensions, maximum chunk tokens, overlap and chunker version.
- Unknown settings on an existing index, changed settings and actual vector
  table width mismatches fail before document processing/state recovery. Only
  an unused index can initialize its metadata automatically. Metadata is checked
  again under the write lock before generated vectors are stored.
- Added `chunker_version` schema migration. Pre-existing settings rows receive
  legacy version 1, so corrected version 2 requires an explicit full rebuild.
  The metadata table remains a singleton describing the current text index.
- Added `reindex_all` and `esper reindex`. The CLI loads the model first. A reset
  transaction clears chunks/FTS, recreates the vector table using the loaded
  model's dimensions, saves settings and queues all documents. Originals,
  document metadata and tags are preserved. Reset failures roll back the old
  index; after a successful reset the old index is replaced, not retained as a
  fallback. The rebuild then commits documents individually through the queue.
- Interrupted rebuilds resume with `esper index`; completed documents are
  skipped. Repeating `esper reindex` restarts every document, including errors.
  Ctrl+C returns 130 with recovery guidance. Empty index/reindex commands do not
  load the model; model and reset errors have readable CLI messages.
- Fixed oversized words with measured Unicode-character splitting. Invalid
  budgets or a single character exceeding the budget raise an explicit error.
  No tokenizer-specific decoding or truncation is used.
- Full suite: 279 passing tests, including settings migration, persistence,
  compatibility rejection, index replacement across 1024/768 dimensions with
  lightweight embedders, reset rollback, preservation of primary data, CLI
  failures, Ctrl+C and resume. Tests use temporary databases/archives.
- Offline real bge-m3 check passed: `contratto` repeated 500 times has 999 tokens
  and now produces four 249-token chunks with no character loss. A temporary CLI
  workflow imported two documents, indexed them, rejected unknown metadata,
  rebuilt and verified six aligned chunks/FTS entries/normalized float32 vectors
  of 1024 dimensions. The real project archive/database was not used.
- Updated USAGE.md and docs/ARCHITETTURA.tex; rebuilt docs/ARCHITETTURA.pdf.
  docs/ remains ignored by Git. Frontend and dependencies are unchanged.
- Future model-specific loading/prompts (including EmbeddingGemma 2) still need
  their own integration; dimension-changing rebuild support is now verified.
  Phase 3 implementation followed below. Desktop toolkit and transport remain
  undecided; no desktop or HTTP runtime has been introduced.

## Phase 3 search implementation — 2026-11-13

- The user explicitly authorized implementing actual retrieval. Added
  `esper/search.py`: exact cosine neighbors via sqlite-vec scalar distance,
  FTS5/BM25 keyword retrieval, reciprocal rank fusion (constant 60), document
  grouping and up to three source passages. Documents are ranked by the best
  passage, without summing votes from their other chunks.
- Shared SQL prefilters require status `indexed` and every normalized requested
  tag before ranking limits. The candidate window starts normally at 50 per
  branch and expands if long documents prevent enough distinct document hits.
  Scalar vector ranking avoids vec0 KNN's 4096-neighbor cap and has stable ties.
- Natural-language keywords become quoted literal Unicode words joined by OR;
  raw FTS syntax is not exposed. Keyword-only search does not load a model or
  require embedding settings. There is no Italian stemming, automatic prefix
  expansion or calibrated semantic relevance threshold.
- Added `Embedder.embed_query`, separated from document embedding for future
  model instructions. bge-m3 still uses its existing normalized encoding. Query
  context limits include special tokens and reject oversize rather than truncate.
  EmbeddingGemma 2 loading/prompts remain future work; no model switch occurred.
- Semantic/hybrid search uses read-only `check_index_settings` before inference
  and again inside a consistent read snapshot shared by both branches and source
  passage reads. Query inference runs before that snapshot. Search does not
  initialize metadata, mutate indexes, or commit a caller's transaction.
- Added `esper search "description"` with `--tag` (repeatable AND), `--limit`
  (default 5), `--mode hybrid|semantic|keyword` and `--json`. Text output includes
  IDs, names, scores, tags and shortened passages; JSON has full text and internal
  snake_case metadata, not the future HTTP contract. Scores are ranks, not
  relevance probabilities. No results is exit 0; errors return 1; Ctrl+C is 130.
  Empty eligible sets skip model loading, as does keyword-only search.
- Full suite: 362 passing tests. Search tests cover literal input, BM25/cosine
  order, RRF, document grouping, AND prefilters, status exclusion, 768-dimensional
  retrieval, read snapshots while another connection deletes a document,
  model compatibility, invalid vectors, CLI failures and query context limits.
- Added `esper/evaluation.py`, `scripts/evaluate_search.py` and a fixed fictional
  Italian corpus in `evaluation/demo.json` (20 documents, 40 labelled queries).
  The tool builds only temporary archives, reuses one loaded model, computes
  recall@1/5/10 and supports hybrid/semantic/keyword comparison and JSON details.
- Offline bge-m3 evaluation passed: hybrid and semantic recall@1=0.9875,
  recall@5=1.0 and recall@10=1.0; keyword recall@1=0.9375, recall@5=0.975 and
  recall@10=1.0. One query has two relevant documents, limiting recall@1 to 0.5
  on that query. This small labelled development fixture is not an independent
  benchmark, large-archive latency test or quality guarantee on personal data.
  Representative real-archive relevance evaluation remains outstanding.
- A separate offline real-model CLI check passed import, indexing, hybrid
  retrieval of a boiler receipt, a semantic paraphrase with tag filtering,
  numeric keyword lookup and full JSON output in a temporary three-document
  archive. Project archive/database and frontend were untouched by verification.
- Updated USAGE.md, evaluation/README.md and architecture source/PDF. The latter
  remain ignored by Git. No dependencies, desktop shell or web server were added.
- At this checkpoint search was available through CLI/core only. Native desktop
  integration followed below and supersedes the earlier Svelte prototype.
  The user still handles commits and pushes.

## Native desktop replacement — 2026-11-13

- The user explicitly changed the UI goal: replicate the approved interface as
  a native desktop app and completely remove the web interface. This supersedes
  the intermediate request to connect the existing Svelte UI over HTTP.
- Implemented Python/Qt Widgets in `esper/desktop/`, using PySide6 Essentials
  (installed/locked version 6.12.0). No Qt WebEngine, browser, HTTP server, Rust
  shell or JavaScript runtime is used. FastAPI dependencies were not added.
- Launch with `uv run esper desktop`; `--data-dir PATH` selects a separate
  archive. `esper-desktop` is also registered as a GUI entry point. Default data
  remain the existing project `data/` archive. Qt/model imports stay lazy for
  unrelated CLI commands, and `desktop --help` does not open the database.
- Native service operations reuse storage, tags, index settings, chunking and
  hybrid search. The service is Qt-independent. One worker QThread serializes
  import, indexing, search and mutations, with one SQLite connection per
  operation and one lazily loaded/reused embedding model.
- Reproduced the Italian monochrome optical console: prominent natural-language
  query, real archive recall frames, angular framing, grid/list cards, sorting,
  type/tag filters, semantic/hybrid/keyword modes and readable source passages.
  Theme, motion, view, sort, mode and geometry persist in desktop.ini per archive.
  Qt's reduced-motion hint is honored when available, including changes at runtime.
- Native picker/drop import indexes files in the background; pending/interrupted
  work resumes at startup. Progress displays actual statuses, without fabricated
  percentages. Search generations discard outdated queued queries and results;
  active queries refresh when newly imported documents finish indexing.
- Native document dialog previews original TXT/Markdown, avoiding duplicated
  overlap text; large previews stop at 2 MB without corrupting UTF-8 boundaries.
  Source passages, metadata, atomic tag replacement, original opening, retry and
  confirmed deletion are wired to the real archive. Images preview natively;
  PDFs open in the system reader. PDF extraction/OCR/image retrieval remain later.
- Full rebuilding requires explicit confirmation in the UI. Unknown/incompatible
  metadata produces an Italian rebuild message. Closing requests cooperative
  stop between documents, lets the active operation finish and preserves the
  remaining queue. Added optional progress/stop callbacks to core queue helpers.
- Removed the complete frontend/ directory, including Svelte/TypeScript, Vite,
  npm manifests/lockfile, mock API/data, generated demo photo and build artifacts.
  Removed docs/API_CONTRACT.md. Root DESIGN.md records the native design. Earlier
  dated web-prototype paths below are historical, not current files.
- Full suite: 386 tests pass. Automated verification uses Qt's offscreen platform and only temporary archive
  folders/preferences. The suite covers service operations, real signal/event
  flow, import/search, tag editing/filtering, reader, themes, image preview,
  confirmed deletion, stale results, rebuild recovery and closing during blocked
  inference with an unfinished document left queued. CLI tests cover lazy Qt
  imports and selecting a separate archive without opening the default database.
- Real bge-m3 verification used Qt's normal event loop and a temporary archive of
  eight fictional documents. Import/indexing, correct hybrid retrieval of the
  boiler document, source preview, themes and clean worker shutdown passed.
  Screenshots are in /tmp/esper-native-{empty,home,search,reader,light}.png and the
  temporary review harness is /tmp/esper_native_review.py. The user's real archive
  was not used for tests. No demo documents are seeded into the native app.
- Updated README, USAGE, DESIGN and architecture source/PDF. Source launch is
  supported; standalone installers and release packaging remain pending phase 9.
  bge-m3 remains active. Future EmbeddingGemma 2 adapters are still separate work.
  Next planned format milestone is PDF extraction; representative real-archive
  retrieval evaluation also remains useful. Do not claim either is complete.

## Versioned benchmarks and digital PDFs — 2026-11-14

- The user authorized a reproducible bge-m3 benchmark, reusable for future Gemma
  comparisons and file formats, followed by PDF support. Both are implemented.
  bge-m3 remains active; no Gemma loading/prompt adapter or OCR was added.
- Added `esper/benchmark.py`, `scripts/benchmark.py`, fixed manifests
  `evaluation/benchmark-v1.json` (45 documents, 85 queries) and
  `evaluation/pdf-v1.json` (10 real fictional PDFs, 23 queries), plus PDF assets.
  The earlier `demo.json`/evaluation runner are retained. Manifests support
  inline text or relative asset paths, stable IDs, binary relevance, tags,
  slices and optional one-based page labels. Asset bytes and labels contribute
  to a fingerprint; duplicate content, invalid labels and changed assets fail.
- Every run creates a temporary archive/index at the actual model dimension.
  A callable model factory is the future adapter boundary; CLI stays bge-m3.
  Added optional embedding revision loading; benchmark pins the cached model
  snapshot when available (recorded baseline revision:
  `5617a9f61b028005a4858fdac845db406aefb181`).
- Reports include recall/hit/nDCG@1/5/10, MRR@10, per-query rankings and timings,
  slices, separate unanswerable empty-result rates, PDF page hit and first-page
  accuracy. Runtime includes model load, import/indexing, warm search median/p95,
  SQLite size and process lifetime peak RSS. CPU/package/thread/source metadata
  and protocol are recorded. Comparisons reject different tasks/protocols and
  flag changed environments/configurations. Output files are never overwritten.
- Offline CPU baselines are saved under `evaluation/results/`; prefer pinned
  `bge-m3-text-v1-final.json` and `bge-m3-pdf-v1-final.json`. Text recall@5:
  semantic 0.9939, hybrid 0.9390, keyword 0.8902. Median text search: approximately
  132/135/11 ms respectively on this machine. Text build: 50 chunks in 19.32 s,
  model load 7.00 s, process peak RSS about 2.08 GiB. Before/after PDF support,
  all text ranking metrics were unchanged. These are small synthetic development
  fixtures, not independent benchmarks or personal-archive quality guarantees.
- PDF recall@5: semantic and hybrid 1.0, keyword 0.9091. First expected page in
  the top document's first passage: semantic 22/22, hybrid 18/22, keyword 13/22.
  Semantic/hybrid have no calibrated rejection threshold; unfiltered queries
  without a relevant document still return neighbors. No ranking tuning or
  default search-mode change was made in response to benchmark results.
- Installed/locked PyMuPDF 1.28.2. `extract_document` returns source sections;
  `index_document` chunks each PDF page independently (overlap never crosses a
  page), then `write_chunks` stores page metadata atomically with all indexes.
  `extract_text` remains available. TXT/Markdown chunk behavior is unchanged.
  Repeated complete margin blocks are removed only within outer 50 points on
  at least three and half the pages. MuPDF dehyphenation is supplemented with
  lowercase line-ending fragment joining; genuine split compounds can still
  lose hyphens. Complex layout/table extraction remains limited.
- Idempotent nullable migrations add `chunks.page`, `documents.page_count` and
  `extraction_warning` without relabelling/rebuilding existing text vectors.
  PDFs with no text, password protection or corruption have explicit errors;
  mixed/blank pages generate partial-search warnings without changing physical
  page numbers. Warnings appear in desktop cards/reader and CLI indexing stderr.
  Previously errored PDFs require retry from the reader or explicit reindexing.
- Search passage objects and CLI JSON/text include PDF page references. Native
  PDF preview renders bounded images in the archive worker, fits the viewport
  width, opens at the best matching page and supports page selection/navigation.
  Generation IDs discard stale preview responses. Opening the original in a
  system reader remains available. No web runtime was introduced.
- Full suite: 416 passing tests using temporary archives, covering benchmark
  metrics/fingerprints/isolation/dimension changes, migrations, page boundaries,
  margin cleanup/dehyphenation, blank/encrypted/corrupt PDFs, rollback, CLI page
  output/warnings, native matching-page preview/navigation and stale responses.
  A separate offline real bge-m3 native event-loop check passed import/indexing,
  paraphrase search and preview on page 2. Harness and captures:
  `/tmp/esper_pdf_real_review.py`, `/tmp/esper-pdf-{reader,results}.png`.
- Updated README, USAGE, DESIGN, evaluation guides/results summary and architecture
  source/PDF. `docs/` remains ignored. No real archive files/database were used or
  modified by this milestone. The user still handles commits and pushes.
- Next planned format work is OCR/scanned documents and images (phase 6).
  Representative real-world retrieval evaluation and investigating hybrid
  regressions remain useful follow-ups; neither is claimed complete.

## Archive reset and desktop review — 2026-11-14

- At the user's explicit request, cleared the default `data/esper.db` and
  `data/files/` for manual import testing. The two previously archived documents
  and database were backed up to `/tmp/esper-before-reset-20261114-155426` first.
  Recreated the empty schema and verified zero documents, tags, chunks, FTS rows,
  vectors and index settings. Desktop preferences and external source files were
  preserved. This was requested maintenance, not use of real data for tests.
- Clarified that current import copies files and deduplicates by content hash;
  it does not retain only source paths. Asked whether the user wants path-only
  storage; no answer received during this change. Storage behavior is unchanged;
  do not record path-only support or a settled preference as implemented.
- Reviewed native Qt layouts at 1040×650 with temporary documents in dark/light
  themes. Fixed horizontal tag overflow, clipped filenames in cards and reader,
  reduced sidebar spacing to leave more room for tags, and removed mismatched
  hero child backgrounds. Elided text remains available via tooltips and
  accessible names; tag actions retain the full underlying tag.
- Empty filtered views now explain the lack of matching documents. Tag/retry/
  delete failures remain visible inside an open reader instead of appearing
  only behind it. Tag editing starts at the beginning of the field.
- Full suite: 389 passing tests, including long names/tags in the small window,
  filtered empty states and failed tag saves preserving input. All verification
  used temporary archives. Review captures are `/tmp/esper-audit-*-after.png`.

## Backend checkpoint — 2026-10-29

- The user explicitly resumed phase 2, step 7: full reindexing and tracking
  the settings used to build the index. Continue in the guide role; the user
  writes application code and the assistant handles supporting tests.
- Keep bge-m3 as the active model and set aside Gemma work for now. The earlier
  discussion concerned future support for either text model, not mixing their
  vectors. Gemma download completion has not been checked since that discussion.
- The user favors eventual desktop delivery. Continue building the CLI/core
  with reusable boundaries; no desktop framework has been selected or added.
- Current inspection still shows the pipeline and CLI from commit `50ffb17`;
  index-settings tracking and full reindexing remain unimplemented. The known
  oversized-word chunking gap must also be fixed before phase 2 is complete.
- On 2026-10-31 the user implemented the frozen `IndexSettings` dataclass in
  `esper/index_settings.py`, with model name, dimensions, chunk maximum and
  overlap fields. A lightweight check verified construction, equality,
  detection of different settings, immutability, and no heavy model imports.
- The user added the `index_settings` table in `esper/db.py`, with a singleton
  row and constraints for positive dimensions/chunk maximum and valid overlap.
  Added 19 supporting schema test cases, including persisted settings and an
  existing index receiving the empty metadata table without changing its data.
  The full suite passed: 214 tests. Only temporary databases were used.
- The next guided step is `get_index_settings(conn)` in
  `esper/index_settings.py`, returning `IndexSettings` or `None` when no row
  exists. Read/write helpers and pipeline integration are not implemented yet.
  Existing indexes without metadata must not be labelled automatically from
  the current configuration.

## Historical web interface redesign — 2026-10-27 (removed 2026-11-13)

The following records the removed prototype and its design feedback. The native
desktop checkpoint above describes the current implementation.

- The user explicitly deferred backend phase 2, step 7 to focus on a complete
  redesign of the existing Svelte frontend. Do not resume step 7 automatically.
- For this redesign, the user explicitly authorized the assistant to implement
  the changes directly. The guide role remains the default for backend work.
- The user confirmed that **natural-language search is Esper's main activity**.
  Emphasize it on the starting screen; archive browsing is secondary.
- Requested direction: minimal, modern, black/white/grayscale dark theme and a
  corresponding light theme. Keep the existing Italian interface language.
- The user rejected the first generic minimal workspace as insufficiently
  distinctive. Esper's visual identity should feel futuristic and draw on its
  Blade Runner namesake and the user's Ted Chiang inspiration: an instrument
  for recalling images from the past. Do not guess the exact story title.
- The current iteration is an optical memory-retrieval console: angular frames,
  fine grid/ruler/focus marks, monospace chrome, a prominent natural-language
  query, and an interactive archive-image recall viewer (`MemoryField.svelte`).
  Preserve the monochrome palette and usability; avoid fake telemetry.
- The user approved this optical concept and then requested less unnecessary
  text and larger, more readable type. Removed repeated slogans, protocol labels,
  decorative references and reader explanations. Kept the main search prompt,
  one short description, useful example queries, file metadata and error states.
  Navigation/file names are approximately 14px, search input 16–17px, passages
  15px, secondary labels 11–12px; mobile keeps readable sizes. Do not reintroduce
  tiny decorative copy to make the interface feel futuristic.
- Added short image scan/focus transitions, slow optical-ring motion, and brief
  document reveals. The header pause control persists `esper.motion`; the system
  reduced-motion setting is also respected.
- A generated grayscale demo photograph is saved in
  `frontend/public/demo/memory-coast.png` and used by the existing mock coastal
  image. It is fictional demonstration data. Its generation prompt, provenance,
  and the design direction are documented in `frontend/DESIGN.md`.
- The redesign lives in the existing frontend checkout, with no new runtime
  dependencies or hosted deployment. The backend and archive were not changed
  during the redesign.
- Implemented a prominent search home with example queries and recent files;
  full archive navigation with type/tag filters, sorting and grid/list views;
  results emphasizing source passages and page references; and a native modal
  document reader with preview/passages tabs, metadata, tag editing, original
  file opening and confirmed deletion. Mobile navigation and themes are included.
- Added grayscale design tokens in `frontend/src/lib/theme.css`, keyboard
  shortcuts (`/`, Ctrl/Cmd+K), keyboard tab navigation, and protection against
  stale responses after changing a search query. Theme/view/sort preferences
  remain persisted locally.
- The frontend continues to use the existing mock API by default. UI search is
  simulated; real natural-language backend search is still phase 3 and API
  integration phase 4. Do not represent the redesign as implementing either.
- `npm run check` passed with zero errors/warnings; `npm run build` passed.
  Browser checks using local Chromium covered search, filtering, sorting,
  previews/passages, tags, upload, processing, deletion, theme persistence and
  mobile layouts with no runtime errors. Screenshots and the temporary browser
  review script are under `/tmp/esper-ui-*`; no new browser test dependencies
  were added to the project. Frontend README documents the new UI and shortcuts.
- The second visual iteration also passed browser checks for selecting/opening
  recall frames, persisted animation pause/resume, and OS reduced-motion support.
  The complete existing browser interaction review still passes without runtime
  errors. The generated demonstration photo is served locally by the app.
- The latest minimal-copy/readability pass also passed `npm run check` (zero
  errors/warnings), `npm run build`, and the complete browser interaction review.
  A focused typography review verified larger text and layouts at 1440px, 390px,
  and 320px, including mobile grid/list, sorting, and no horizontal overflow.
  Thumbnail headings no longer shrink under long excerpts; sorting controls
  retain enough width for their labels. No new assets or dependencies were added.
- Next, collect the user's feedback on the design and refine the interface.

## Documentation audit — 2026-10-27

- After approving the interface, the user requested updating USAGE.md and
  checking alignment with docs/ARCHITETTURA.tex. USAGE.md now covers the real CLI
  workflow, frontend startup and Node requirements, browser controls and saved
  preferences, mock-data separation, chunk inspection, and frontend checks/build.
- ARCHITETTURA.tex now distinguishes implemented schema/pipeline from planned
  architecture, records the UI work as a prototype refinement rather than phase
  4 completion, documents the rowid/trigger design and verified prefilter support,
  and marks model/settings tracking and full reindexing as pending phase 2 step 7.
  The PDF was rebuilt successfully and copied to docs/ARCHITETTURA.pdf. The docs/
  directory remains ignored by Git, as previously chosen by the user.
- The audit re-ran all existing tests: 195 passed. It also found a real discrepancy
  in chunking.py: a single unbroken word exceeding the token budget remains whole.
  Using the cached bge-m3 tokenizer, `text = 'contratto' * 500` yields 999 tokens
  and a single 999-token chunk with a configured maximum of 400. The word-count
  tests do not establish the real-token limit for this edge case.
- This is a known implementation gap, not a newly relaxed architectural
  requirement. It is documented in USAGE.md and ARCHITETTURA.tex. Application
  code was not changed during the audit. When the user resumes backend work,
  guide them through addressing it as well as the pending reindexing/settings
  step before declaring phase 2 complete. Do not resume backend implementation
  automatically merely because the issue is recorded here.

## EmbeddingGemma 2 compatibility review — 2026-10-28

- At the user's request, reviewed `google/embeddinggemma-2` against the current
  embedding wrapper and indexing pipeline. This was research, not a decision
  to replace bge-m3 or permission to start the next backend milestone.
- Local Hugging Face cache contains bge-m3, with no Gemma model found in the
  checked caches/model directories. The local Ollama list contains only
  `glm-ocr:q8_0`; no Gemma model is installed there.
- Installed packages are sentence-transformers 6.1.0, transformers 5.19.0,
  and torch 2.14.1+cpu. Offline inspection confirmed the installed Transformers
  recognizes EmbeddingGemma2Config and SentenceTransformer supports
  `config_kwargs` for disabling unused modality encoders. No Gemma weights
  were downloaded and no real Gemma inference was performed.
- Future text support can reuse the pipeline, but needs document/query prompts,
  suitable loading options, and index settings tracking plus full rebuilding.
  Gemma outputs 768 dimensions; the present schema expects 1024. A temporary
  in-memory database confirmed that inserting a 768-dimensional vector fails.
  Changing the config alone cannot migrate an existing vector table.
- Gemma's multimodal capabilities would require additional media processing
  and index metadata; the current backend extractor supports only TXT/Markdown.
  Quality and CPU speed relative to bge-m3 have not been measured for Esper.
- Application code and the real archive/database were left unchanged.

## Backend checkpoint — 2026-10-27

- Phase 2, step 5: the user has implemented `set_status` in `esper/indexing.py`.
  It was reviewed and checked against a temporary on-disk database: updates
  persist, omitted error messages clear old errors, explicit messages are
  stored, and an invalid status rolls back without changing the saved row.
- Minor optional cleanup suggested: remove the empty string and explicit
  backslash after `conn.execute(`; parentheses already allow line breaks.
- The user has corrected `write_chunks`: FTS insertion is present, each vector
  is serialized individually, and indexed status is set after the loop.
  Pairing uses `zip(..., strict=True)`.
- The user has implemented `index_document` correctly. Phase 2, step 5 is
  complete: extraction, chunking, embedding, transactional storage, and error
  recording are connected.
- `tests/test_indexing.py` now has 23 tests, including pipeline integration
  with a lightweight test embedder, empty files, reindexing, unknown IDs,
  extraction/model/storage errors, preservation of an earlier index after
  failure, processing status outside a write transaction during embedding,
  and propagation of KeyboardInterrupt.
- The full suite passed: 195 tests, using
  `.venv/bin/python -m pytest -q -p no:cacheprovider`.
- A separate offline check with the cached real bge-m3 model also passed:
  a temporary Markdown document produced 2 chunks, 2 FTS entries, and 2
  normalized float32 vectors of 1024 dimensions; status became indexed.
  Both archive files and the database were temporary; project data was untouched.
  Importing `esper.indexing` was also checked not to load PyTorch.
- The whole pipeline and the internal chunking helper calls have been explained
  with a diagram and example. Keep connecting new code to that flow.
- The user has implemented `index_queued` correctly. Five new tests verify
  sequential processing with the supplied embedder, counts, continuation after
  a document fails, recovery of interrupted processing, preservation of already
  indexed/error documents, no pending work, and Ctrl+C followed by resume without
  repeating completed work.
- Phase 2, step 6 is complete. The user registered and implemented `esper index`
  in `esper/cli.py`. It checks for queued/processing documents, lazily loads one
  model, runs the queue, reports only this run's document errors on stderr,
  and returns exit code 1 for document failures or model-loading failures.
  No work means no model import/loading. Already errored documents are skipped.
- Eleven new CLI tests verify parsing, no pending work, model reuse, recovery,
  mixed/all-document failures, old-error exclusion, import/load failure, and
  lazy imports in a fresh Python process. The full suite has 195 passing tests.
- An offline real-model CLI check with a temporary database/archive also passed:
  import 2 documents, index to 3 aligned chunks/FTS entries/vectors, run index
  again with no pending work, and list both as indexed. Project data was not used.
- USAGE.md now documents `esper index`, processing/recovery/error behavior, and
  the fact that search and full reindexing remain pending.
- When the user returns to backend work, phase 2, step 7 remains: full reindexing
  and tracking the model/dimensions and chunking settings used to build the index.
  The user deferred this step to work on the interface. Explain why these settings
  matter before proposing schema or code. The earlier `embedding_models` table
  was deferred to this step; its final design is not yet settled. Do not move on
  to phase 3 search until phase 2 is verified complete.
- The assistant has edited supporting tests, USAGE.md, and this file, not
  application code. The user handles commits and pushes; this is a useful
  checkpoint before starting step 7.
- Earlier snapshots below describe the state before the status helper was added.

## Earlier checkpoint — 2026-10-24

This is a dated snapshot, not a substitute for inspecting the current repository.

- Phase 1 is complete: archive storage, content deduplication, tags, deletion,
  and CLI commands `import`, `list`, `tag`, `untag`, and `delete`.
- Phase 2 is in progress. Text extraction for `.txt` and `.md`, chunking, and the
  `Embedder` wrapper are implemented. Chunk settings are 400 tokens with up to
  50 tokens of overlap.
- Latest commit at this checkpoint: `9336914`, adding the `chunks`, `chunks_fts`,
  and `chunks_vec` tables and deletion cleanup, with tests.
- `esper/indexing.py` is empty. The immediate next implementation topic is the
  indexing pipeline for one document: processing status, extraction, chunking,
  embeddings, transactional writes with matching chunk IDs across the three
  tables, and indexed/error status.
- Later phase 2 work includes processing queued documents sequentially,
  recovering interrupted processing, and full reindexing. The roadmap mentions
  an `embedding_models` table that is not currently implemented; the prior
  Claude discussion proposed deferring it to step 7 to design index settings
  tracking alongside reindexing (see the recovered context below).
- Hybrid search is phase 3; FastAPI and frontend integration are phase 4. The
  Svelte frontend currently uses mock data by default.
- Existing suite verified on this date: 161 tests passed using
  `.venv/bin/python -m pytest -q -p no:cacheprovider`. The actual embedding model
  was not loaded during this review.
- At this checkpoint, `esper/embedding.py` has a pre-existing uncommitted change
  adding a trailing blank line. Leave it intact.
- No indexing implementation has been started by the assistant. The user has
  clarified the guide role; begin the next coding discussion with a small
  explanation of the one-document pipeline and its first step.

## Recovered Claude context — 2026-10-26

At the user's request, the assistant read the Esper-specific Claude memories
and relevant chat turns in
`/home/maurizio/.claude/projects/-home-maurizio-Scrivania-Progetti-Esper/`.
These established the collaboration details above. There is no need to reread
the full history routinely; inspect it only when a specific uncertainty matters.

- The October 22 conversation already supplied a proposed step 5 implementation:
  `set_status`, `write_chunks`, and `index_document`. It was guidance, not code
  written into the project. On October 26, `esper/indexing.py` is still empty
  and HEAD is still `9336914`.
- The proposal computes extraction, chunks, and embeddings outside the database
  write transaction. It then replaces old chunks, writes all three tables with
  matching IDs, and marks the document indexed in one transaction. Document
  processing failures are recorded with error status.
- `index_document` receives an existing embedder. Avoid importing the heavy
  embedding module just for type annotations; earlier measurements showed that
  this would slow down unrelated CLI commands. The proposed approach uses
  `TYPE_CHECKING` and a quoted `Embedder` annotation.
- The prior plan deferred `embedding_models`/index settings to step 7, where
  model, dimensions, and chunking settings can be considered together. Its
  absence is not a newly discovered blocker for step 5.
- A comparison with an alternative embedding model was deferred by the user.
  Continue with bge-m3 unless the user asks to revisit model selection.
- The next small coding step is the status helper in `esper/indexing.py`, then
  transactional chunk storage and the orchestration function, with explanation
  and review between steps. No application code has been changed in this review.
