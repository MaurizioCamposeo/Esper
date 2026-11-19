# Esper

> *"Enhance."* — Blade Runner

Esper is a personal document archive with **semantic search**. Instead of remembering a file name or the exact words it contains, you describe what you are looking for in your own words, for example *"where did I put the house contract"*, and Esper finds the documents about that topic.

Everything runs **locally**, on your own computer: your documents never leave your machine.

## Status

**Working native desktop application and CLI.** Import TXT, Markdown, digital PDFs,
and JPEG or PNG images, search by meaning and keywords, inspect source passages,
and organize the local archive with tags. The desktop uses Qt widgets and calls Python directly.
Open **Mappa 3D** to explore files by similarity, inspect links between related documents, and open a file in the reader. The map reuses saved passage embeddings and caches its coordinates locally.
PDF results include page numbers and open the native preview on the matching page.
Esper runs OCR and generates a detailed visual description for every JPEG and PNG.
Search can match either the readable words or the depicted scene. See the [image setup](USAGE.md#jpeg-and-png-images). OCR for scanned
PDF pages is a separate upcoming step.

```bash
uv sync
uv run esper desktop
```

Drag documents into the window or choose **Aggiungi documenti**. Indexing runs in
the background; the model is downloaded on first use if it is not cached.
For an older index, use **Ricostruisci indice** when prompted. Archived originals
and tags are preserved by rebuilding.

See [USAGE.md](USAGE.md) for commands, desktop controls and evaluation, and
[DESIGN.md](DESIGN.md) for the native interface design. Standalone installers are
future work; the source application currently launches through uv.

Versioned text and PDF benchmarks, saved bge-m3 results and comparison commands
are documented in [evaluation/BENCHMARK.md](evaluation/BENCHMARK.md).

## What it will do

- Store and search text documents, digital PDFs, JPEGs and PNGs
- Find them by describing what they contain, not just by keywords
- Organize them with tags
- Later on: answer questions by citing the documents it finds
