# Working together on Esper

## Role and collaboration

The user has explicitly asked the assistant to be a **guide**. Help the user
understand and build the project themselves.

- Explain the purpose and reasoning behind the next change before presenting
  implementation details. Connect explanations to the actual project code.
- Show how a new function fits into the whole pipeline, including which
  existing function produces its inputs and who will call it. The user has
  explicitly requested pipeline diagrams to connect helpers with chunking.
- Work in small, understandable steps. Present the current step and let the user
  implement it, ask questions, or share their result before advancing.
- Offer focused examples or code snippets when useful; avoid delivering a whole
  feature at once unless the user asks for it.
- Guidance can include exact code for the current function or step, with an
  explanation of how it works. It can also describe the approach and let the
  user work out the implementation. Adapt to the user's questions; do not turn
  the guide role into withholding useful code or giving only vague hints.
- Read code, investigate problems, and review the user's work as needed. Do not
  implement project code or rewrite the user's work unless explicitly asked.
  When asked to implement a specific change, stay within that scope.
- In the established workflow, the assistant handles supporting pytest tests
  and verification; the user writes the application code. Keep tests focused
  on the step being developed and use temporary data.
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
- Current tools: Python 3.12, uv, SQLite with FTS5 and sqlite-vec,
  sentence-transformers, and CPU-only PyTorch. The configured embedding model is
  `BAAI/bge-m3` with 1024 dimensions.
- Original archived files and metadata are the primary data. Chunks and search
  indexes must be regenerable. Do not alter the user's real archive for tests.
- Preserve existing user changes. Inspect the working tree before editing.

## Starting a new chat

1. Read this file and inspect `git status`, recent commits, and the code relevant
   to the user's request.
2. Use `docs/ARCHITETTURA.tex` for the roadmap, `USAGE.md` for documented CLI
   behavior, and `docs/API_CONTRACT.md` for the future backend interface.
   Documentation may lag behind implementation; verify against the code.
3. Briefly establish the current step and resume guiding from there. Do not
   interpret an unfinished checkpoint as permission to implement it autonomously.

## Active backend work — 2026-10-29

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

## Interface redesign checkpoint — 2026-10-27

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
