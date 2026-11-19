"""Versioned end-to-end retrieval benchmarks using disposable archives only."""

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version, PackageNotFoundError
import json
import math
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

from esper.db import connect, init_schema, recreate_vector_index
from esper.indexing import current_index_settings, index_queued
from esper.search import SEARCH_MODES, RRF_CONSTANT, search_documents
from esper.storage import import_file
from esper.tags import add_tag, normalize_tag

REPORT_VERSION = 1
PROTOCOL = {"version": 1, "limit": 10, "candidate_limit": 50, "max_passages": 3,
            "rrf_constant": RRF_CONSTANT, "relevance": "binary", "warmups_per_mode": 1}


def _strings(value, field, *, allow_empty=True):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{field} must be an array of nonempty strings")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must not contain duplicates")
    return value


def load_benchmark(path: Path) -> dict:
    """Validate a manifest and fingerprint its labels and exact document bytes."""
    path = path.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Benchmark schema_version must be 1")
    for field in ("name", "version", "description"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"Benchmark requires {field}")
    documents, queries = data.get("documents"), data.get("queries")
    if not isinstance(documents, list) or not documents or not isinstance(queries, list) or not queries:
        raise ValueError("Benchmark needs nonempty documents and queries arrays")
    keys, hashes = set(), set()
    for doc in documents:
        if not isinstance(doc, dict) or not isinstance(doc.get("key"), str) or not doc["key"].strip() or doc["key"] in keys:
            raise ValueError("Document keys must be unique nonempty strings")
        keys.add(doc["key"])
        if not isinstance(doc.get("format"), str) or not doc["format"].isalnum():
            raise ValueError("Each document needs an explicit format")
        if ("text" in doc) == ("path" in doc):
            raise ValueError("Provide exactly one of text or relative path per document")
        if "text" in doc:
            if doc["format"] not in ("txt", "md") or not isinstance(doc["text"], str) or not doc["text"].strip():
                raise ValueError("Inline text requires nonempty TXT or Markdown")
            content = doc["text"].encode("utf-8")
        else:
            if not isinstance(doc["path"], str) or Path(doc["path"]).is_absolute():
                raise ValueError("Asset paths must be relative to the manifest")
            asset = (path.parent / doc["path"]).resolve()
            if not asset.is_relative_to(path.parent) or not asset.is_file():
                raise ValueError("Asset must be a file inside the dataset directory")
            if asset.suffix.lower() != "." + doc["format"]:
                raise ValueError("Asset extension must match format")
            content = asset.read_bytes()
            doc["_asset"] = asset
        digest = sha256(content).hexdigest()
        if digest in hashes:
            raise ValueError("Duplicate document content would be deduplicated by Esper")
        hashes.add(digest)
        doc["sha256"] = digest
        doc["tags"] = sorted({normalize_tag(t) for t in _strings(doc.get("tags", []), "tags")})
    by_key = {doc["key"]: doc for doc in documents}
    query_ids = set()
    for case in queries:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"].strip() or case["id"] in query_ids:
            raise ValueError("Query IDs must be unique nonempty strings")
        query_ids.add(case["id"])
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise ValueError("Each query needs nonempty text")
        relevant = _strings(case.get("relevant_documents"), "relevant_documents")
        if not set(relevant).issubset(keys):
            raise ValueError("Unknown relevant document")
        case["tags"] = sorted({normalize_tag(t) for t in _strings(case.get("tags", []), "tags")})
        if any(not set(case["tags"]).issubset(by_key[key]["tags"]) for key in relevant):
            raise ValueError("A relevant document is excluded by the tag filter")
        case["slices"] = _strings(case.get("slices", ["general"]), "slices", allow_empty=False)
        pages = case.get("relevant_pages", {})
        if not isinstance(pages, dict) or not set(pages).issubset(relevant):
            raise ValueError("Page labels must refer to relevant documents")
        for key, numbers in pages.items():
            if by_key[key]["format"] != "pdf" or not isinstance(numbers, list) or not numbers or any(type(n) is not int or n < 1 for n in numbers):
                raise ValueError("Page labels require PDF documents and positive one-based pages")
        case["relevant_pages"] = pages
    canonical = {**data, "documents": [{k: v for k, v in doc.items() if not k.startswith("_")} for doc in documents]}
    data["fingerprint"] = sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return data


def ranking_metrics(retrieved, relevant):
    """Binary document metrics; unanswerable queries are evaluated separately."""
    relevant = set(relevant)
    if not relevant:
        return {"empty_result": float(not retrieved)}
    values = {}
    for k in (1, 5, 10):
        found = len(set(retrieved[:k]) & relevant)
        values[f"recall@{k}"] = found / len(relevant)
        values[f"hit@{k}"] = float(found > 0)
        dcg = sum(1 / math.log2(rank + 1) for rank, key in enumerate(retrieved[:k], 1) if key in relevant)
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
        values[f"ndcg@{k}"] = dcg / ideal
    values["mrr@10"] = next((1 / rank for rank, key in enumerate(retrieved[:10], 1) if key in relevant), 0.0)
    return values


def summarize(rows):
    answerable = [row for row in rows if row["relevant_documents"]]
    negatives = [row for row in rows if not row["relevant_documents"]]
    metrics = defaultdict(list)
    for row in answerable:
        for key, value in row["metrics"].items():
            metrics[key].append(value)
    return {"queries": len(rows), "answerable": len(answerable), "unanswerable": len(negatives),
            "metrics": {key: statistics.mean(values) for key, values in metrics.items()},
            "unanswerable_empty_rate": statistics.mean(row["metrics"]["empty_result"] for row in negatives) if negatives else None}


def latency_summary(samples):
    """Nearest-rank p95 and median over measured complete search calls."""
    values = sorted(samples)
    return {"samples": len(values), "median_ms": statistics.median(values),
            "p95_ms": values[math.ceil(.95 * len(values)) - 1], "min_ms": values[0], "max_ms": values[-1]}


def environment():
    packages = {}
    for name in ("sentence-transformers", "transformers", "torch", "numpy", "sqlite-vec", "PyMuPDF"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    root = Path(__file__).resolve().parent.parent
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), cpu)
    source = sha256()
    for path in sorted((root / "esper").rglob("*.py")):
        source.update(str(path.relative_to(root)).encode())
        source.update(path.read_bytes())
    return {"python": platform.python_version(), "platform": platform.platform(), "cpu": cpu,
            "logical_cpus": os.cpu_count(), "packages": packages, "git_head": git("rev-parse", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain")), "source_sha256": source.hexdigest()}


def run_benchmark(data, model_factory, *, modes=SEARCH_MODES, repeats=3, notify=lambda message: None):
    """Build a fresh index and measure production retrieval, never the user archive."""
    if type(repeats) is not int or repeats < 1 or not modes or any(mode not in SEARCH_MODES for mode in modes):
        raise ValueError("Use positive repeats and supported search modes")
    env = environment()
    notify("Loading embedding model…")
    start = perf_counter()
    model = model_factory()
    load_seconds = perf_counter() - start
    settings = asdict(current_index_settings(model))
    underlying = getattr(model, "model", None)
    config = getattr(getattr(underlying, "_first_module", lambda: None)(), "auto_model", None)
    config = getattr(config, "config", None)
    revision = getattr(model, "revision", None) or getattr(config, "_commit_hash", None)
    if "torch" in sys.modules:
        env["torch_threads"] = sys.modules["torch"].get_num_threads()
    with TemporaryDirectory(prefix="esper-benchmark-") as temporary:
        root = Path(temporary)
        conn = connect(root / "benchmark.db")
        try:
            init_schema(conn)
            with conn:
                recreate_vector_index(conn, model.dimensions)
            start = perf_counter()
            ids = {}
            for number, doc in enumerate(data["documents"]):
                path = doc.get("_asset")
                if path is None:
                    path = root / f"source-{number}.{doc['format']}"
                    path.write_text(doc["text"], encoding="utf-8")
                document_id, created = import_file(conn, path, root / "files")
                if not created:
                    raise ValueError("Unexpected deduplication in benchmark")
                actual_hash = conn.execute("SELECT sha256 FROM documents WHERE id = ?", (document_id,)).fetchone()[0]
                if actual_hash != doc["sha256"]:
                    raise ValueError(f"Dataset asset changed after validation: {doc['key']}")
                ids[doc["key"]] = document_id
                for tag in doc["tags"]:
                    add_tag(conn, document_id, tag)
            import_seconds = perf_counter() - start
            notify(f"Indexing {len(ids)} documents…")
            start = perf_counter()
            indexed, failed = index_queued(conn, model, root / "files")
            index_seconds = perf_counter() - start
            if failed:
                errors = [dict(row) for row in conn.execute("SELECT original_name, error FROM documents WHERE status='error'")]
                raise ValueError(f"Benchmark indexing failed: {errors}")
            corpus_metadata = []
            for doc in data["documents"]:
                row = conn.execute("SELECT * FROM documents WHERE id = ?", (ids[doc["key"]],)).fetchone()
                corpus_metadata.append({"key": doc["key"], "format": doc["format"], "sha256": doc["sha256"],
                                        "page_count": row["page_count"], "extraction_warning": row["extraction_warning"]})
            for case in data["queries"]:
                for key, pages in case["relevant_pages"].items():
                    count = conn.execute("SELECT page_count FROM documents WHERE id = ?", (ids[key],)).fetchone()[0]
                    if count is None or any(page > count for page in pages):
                        raise ValueError(f"Page label outside document: {case['id']} / {key}")
            chunk_count = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
            if not chunk_count:
                raise ValueError("Benchmark produced no searchable chunks")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            database_bytes = (root / "benchmark.db").stat().st_size
            reverse = {value: key for key, value in ids.items()}
            reports = {}
            for mode in modes:
                notify(f"Measuring {mode}: {len(data['queries'])} queries × {repeats}…")
                first = data["queries"][0]
                search_documents(conn, first["query"], model, tags=first["tags"], mode=mode, limit=10)
                rows = []
                for case in data["queries"]:
                    samples, rankings = [], []
                    for _ in range(repeats):
                        start = perf_counter()
                        hits = search_documents(conn, case["query"], model, tags=case["tags"], mode=mode, limit=10,
                                                candidate_limit=PROTOCOL["candidate_limit"], max_passages=PROTOCOL["max_passages"])
                        samples.append((perf_counter() - start) * 1000)
                        rankings.append([reverse[hit.document_id] for hit in hits])
                    metrics = ranking_metrics(rankings[-1], case["relevant_documents"])
                    if case["relevant_pages"]:
                        metrics["first_page_hit@1"] = float(bool(hits and hits[0].matches) and
                            getattr(hits[0].matches[0], "page", None) in case["relevant_pages"].get(reverse[hits[0].document_id], []))
                        for k in (1, 5):
                            metrics[f"page_hit@{k}"] = float(any(
                                getattr(match, "page", None) in case["relevant_pages"].get(reverse[hit.document_id], [])
                                for hit in hits[:k] for match in hit.matches))
                    rows.append({**case, "retrieved": rankings[-1], "metrics": metrics, "latency_ms": samples,
                                 "stable_ranking": all(ranking == rankings[0] for ranking in rankings),
                                 "passages": [{"document": reverse[hit.document_id], "pages": [getattr(match, "page", None) for match in hit.matches]} for hit in hits]})
                slices = sorted({name for row in rows for name in row["slices"]})
                reports[mode] = {**summarize(rows), "latency": latency_summary([v for row in rows for v in row["latency_ms"]]),
                                 "slices": {name: summarize([row for row in rows if name in row["slices"]]) for name in slices}, "queries": rows}
        finally:
            conn.close()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"report_version": REPORT_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset": {key: data[key] for key in ("name", "version", "description", "fingerprint")},
            "documents": corpus_metadata,
            "protocol": {**PROTOCOL, "repeats": repeats, "mode_order": list(modes)}, "environment": env,
            "model": {"settings": settings, "revision": revision, "adapter": type(model).__module__ + "." + type(model).__qualname__,
                      "batch_size": getattr(model, "batch_size", None), "device": str(getattr(underlying, "device", "unknown"))},
            "build": {"model_load_seconds": load_seconds, "import_seconds": import_seconds, "index_seconds": index_seconds,
                      "documents": indexed, "chunks": chunk_count, "chunks_per_second": chunk_count / index_seconds,
                      "database_bytes": database_bytes, "process_peak_rss_bytes": peak if sys.platform == "darwin" else peak * 1024},
            "results": reports}


def compare_reports(before, after):
    """Reject different tasks; compare model runs on paired query IDs."""
    if before["report_version"] != REPORT_VERSION or after["report_version"] != REPORT_VERSION:
        raise ValueError("Unsupported report version")
    if before["dataset"]["fingerprint"] != after["dataset"]["fingerprint"]:
        raise ValueError("Dataset fingerprints differ; rerun both models on the same dataset")
    for key, value in PROTOCOL.items():
        if before["protocol"].get(key) != value or after["protocol"].get(key) != value:
            raise ValueError(f"Incompatible benchmark protocol: {key}")
    warnings = []
    for key in ("environment", "protocol"):
        if before[key] != after[key]:
            warnings.append(f"{key} differs; latency comparisons require matched hardware, load and settings")
    old_settings, new_settings = before["model"]["settings"], after["model"]["settings"]
    for key in ("chunk_max_tokens", "chunk_overlap_tokens", "chunker_version"):
        if old_settings[key] != new_settings[key]:
            warnings.append(f"{key} differs: this compares complete configurations, not only embeddings")
    results = {}
    for mode in before["results"].keys() & after["results"].keys():
        old, new = before["results"][mode], after["results"][mode]
        paired = {row["id"]: row for row in old["queries"]}
        if set(paired) != {row["id"] for row in new["queries"]}:
            raise ValueError("Reports contain different query IDs")
        results[mode] = {"metric_delta": {key: new["metrics"][key] - value for key, value in old["metrics"].items()},
                         "median_latency_delta_ms": new["latency"]["median_ms"] - old["latency"]["median_ms"],
                         "regressions": [row["id"] for row in new["queries"] if row["metrics"].get("mrr@10", 0) < paired[row["id"]]["metrics"].get("mrr@10", 0)]}
    if not results:
        raise ValueError("Reports have no common retrieval modes")
    return {"before_model": before["model"], "after_model": after["model"], "warnings": warnings, "results": results}
