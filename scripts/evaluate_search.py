"""Evaluate retrieval on a supplied corpus, using only a temporary archive.

Usage: uv run python scripts/evaluate_search.py --mode all
"""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

from esper.db import connect, init_schema
from esper.evaluation import EvaluationCase, evaluate_search
from esper.indexing import index_queued
from esper.search import SEARCH_MODES
from esper.storage import import_file
from esper.tags import add_tag, normalize_tag

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "evaluation" / "demo.json"


def load_dataset(path: Path) -> dict:
    """Validate labels and corpus fields before loading a model or creating files."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("documents") or not data.get("queries"):
        raise ValueError("Dataset must contain nonempty documents and queries arrays")
    if not isinstance(data["documents"], list) or not isinstance(data["queries"], list):
        raise ValueError("documents and queries must be arrays")
    keys = set()
    contents = set()
    for document in data["documents"]:
        if not isinstance(document, dict) or any(
            not isinstance(document.get(field), str) or not document[field].strip()
            for field in ("key", "text")
        ):
            raise ValueError("Each document requires nonempty key and text strings")
        if document["key"] in keys or document["text"] in contents:
            raise ValueError("Dataset document keys and contents must be unique")
        keys.add(document["key"])
        contents.add(document["text"])
        tags = document.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("Document tags must be strings in an array")
        document["tags"] = [normalize_tag(tag) for tag in tags]
    documents = {document["key"]: document for document in data["documents"]}
    for case in data["queries"]:
        if not isinstance(case, dict) or not isinstance(case.get("query"), str) or not case["query"].strip():
            raise ValueError("Each case requires a nonempty query string")
        relevant = case.get("relevant_documents")
        if not isinstance(relevant, list) or not relevant or any(not isinstance(key, str) or key not in keys for key in relevant):
            raise ValueError("Each case requires known relevant_documents keys")
        tags = case.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("Query tags must be strings in an array")
        case["tags"] = [normalize_tag(tag) for tag in tags]
        if any(not set(case["tags"]).issubset(documents[key]["tags"]) for key in relevant):
            raise ValueError("A relevant document is excluded by its query's tag filters")
    return data


def main(argv: list[str] | None = None) -> int:
    """Build the fixture corpus once, reuse one model and print retrieval metrics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--mode", choices=(*SEARCH_MODES, "all"), default="hybrid")
    parser.add_argument("--json", dest="json_output", action="store_true", help="include all per-query rankings as JSON")
    args = parser.parse_args(argv)
    try:
        data = load_dataset(args.dataset)
        from esper.embedding import Embedder
        model = Embedder()
        with TemporaryDirectory(prefix="esper-retrieval-") as temporary:
            root = Path(temporary)
            conn = connect(root / "evaluation.db")
            try:
                init_schema(conn)
                ids = {}
                for number, document in enumerate(data["documents"]):
                    path = root / f"source-{number}.md"
                    path.write_text(document["text"], encoding="utf-8")
                    document_id = import_file(conn, path, root / "archive")[0]
                    ids[document["key"]] = document_id
                    for tag in document["tags"]:
                        add_tag(conn, document_id, tag)
                _, failed = index_queued(conn, model, root / "archive")
                if failed:
                    raise ValueError(f"Could not index {failed} evaluation documents")
                cases = [EvaluationCase(
                    case["query"], tuple(ids[key] for key in case["relevant_documents"]),
                    tuple(case["tags"]),
                ) for case in data["queries"]]
                modes = SEARCH_MODES if args.mode == "all" else (args.mode,)
                reports = [evaluate_search(conn, model, cases, mode=mode) for mode in modes]
            finally:
                conn.close()
        if args.json_output:
            print(json.dumps([asdict(report) for report in reports], ensure_ascii=False, indent=2))
        else:
            print(f"Synthetic/local fixture: {len(data['documents'])} documents, {len(cases)} queries")
            for report in reports:
                print(f"{report.mode}: recall@1={report.recall_at_1:.3f} "
                      f"recall@5={report.recall_at_5:.3f} recall@10={report.recall_at_10:.3f}")
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
