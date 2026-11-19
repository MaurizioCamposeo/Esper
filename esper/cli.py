# Creating esper CLI command
import argparse
import sys
from pathlib import Path
import sqlite3
import json
from dataclasses import asdict

from esper.config import DATA_DIR, DB_PATH
from esper.db import connect, init_schema
from esper.storage import import_file, get_document, delete_document
from esper.tags import get_document_by_tag, get_document_tags, normalize_tag, add_tag, remove_tag
from esper.indexing import index_queued, reindex_all
from esper.search import SEARCH_MODES, search_documents, searchable_chunk_count, validate_search

def build_parser() -> argparse.ArgumentParser:
    """Define the commands and their arguments."""
    parser = argparse.ArgumentParser(prog="esper", description="Personal document archive.")
    commands = parser.add_subparsers(dest="command", required=True)

    import_cmd = commands.add_parser("import", help="import one or more files")
    import_cmd.add_argument("paths", nargs="+", type=Path, help="files to import")

    list_cmd = commands.add_parser("list", help="list archived documents")
    list_cmd.add_argument("--tag", dest="tags", action="append", default=[], help="only documents with this tag (repeatable)")

    tag_cmd = commands.add_parser("tag", help="add tags to a document")
    tag_cmd.add_argument("document_id", type=int, help="document number as shown by list")
    tag_cmd.add_argument("names", nargs="+", help="tags to add")

    untag_cmd = commands.add_parser("untag", help="remove tags from a document")
    untag_cmd.add_argument("document_id", type=int, help="document number as shown by list")
    untag_cmd.add_argument("names", nargs="+", help="tags to remove")

    delete_cmd = commands.add_parser("delete", help="delete documents and their files")
    delete_cmd.add_argument("document_ids", nargs="+", type=int, help="document numbers as shown by list")
    delete_cmd.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")

    index_cmd = commands.add_parser("index", help="index queued documents")
    commands.add_parser("reindex", help="rebuild all search indexes from archived originals")

    search_cmd = commands.add_parser("search", help="search indexed documents by meaning and keywords")
    search_cmd.add_argument("query", help="a natural-language description (quote multiple words)")
    search_cmd.add_argument("--tag", dest="tags", action="append", default=[], help="require this tag (repeatable, AND)")
    search_cmd.add_argument("--limit", type=int, default=5, help="maximum documents to return (default: 5)")
    search_cmd.add_argument("--mode", choices=SEARCH_MODES, default="hybrid", help="retrieval method (default: hybrid)")
    search_cmd.add_argument("--json", dest="json_output", action="store_true", help="print full structured results as JSON")

    desktop_cmd = commands.add_parser("desktop", help="open the native desktop application")
    desktop_cmd.add_argument("--data-dir", type=Path, default=DATA_DIR, help="archive folder (default: project data folder)")

    return parser

def main(argv: list[str] | None = None) -> int:
    """Entry point of the `esper` command; return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "desktop":
        try:
            from esper.desktop.app import run
            return run(args.data_dir)
        except (ImportError, OSError, sqlite3.DatabaseError) as exc:
            print(f"error: could not start desktop application: {exc}", file=sys.stderr)
            return 1
    conn = connect(DB_PATH)
    init_schema(conn)

    try:
        if args.command == "import":
            return cmd_import(conn, args.paths)
        if args.command == "list":
            return cmd_list(conn, args.tags)
        if args.command == "tag":
            return cmd_tag(conn, args.document_id, args.names)
        if args.command == "untag":
            return cmd_untag(conn, args.document_id, args.names)
        if args.command == "delete":
            return cmd_delete(conn, args.document_ids, args.yes)
        if args.command == "index":
            return cmd_index(conn)
        if args.command == "reindex":
            return cmd_index(conn, rebuild=True)
        if args.command == "search":
            return cmd_search(conn, args.query, args.tags, args.limit, args.mode, args.json_output)
    except ValueError as ve:
        print(f'error: {ve}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        if args.command in ("index", "reindex"):
            print("run 'esper index' to resume pending work, or 'esper reindex' to restart a rebuild", file=sys.stderr)
        return 130
    finally:
        conn.close()

    return 0

def cmd_import(conn: sqlite3.Connection, paths: list[Path]) -> int:
    """Import each path and report what happened; return 1 if any import failed."""
    exit_code = 0
    for path in paths:
        try:
            doc_id, created = import_file(conn, path)
        except FileNotFoundError:
            print(f"error: {path} is not a file", file=sys.stderr)
            exit_code = 1 # at least one file not imported
            continue
        if created:
            print(f"imported #{doc_id} {path.name}")
        else:
            print(f"already present as #{doc_id} {path.name}")
    return exit_code

def format_size(size: int) -> str:
    """Return a human-readable size, e.g. 833 B, 1.5 KiB, 2.1 GiB."""
    for unit in ("B", "KiB", "MiB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"

def cmd_list(conn: sqlite3.Connection, tags: list[str]) -> int:
    """Print one line per document, optionally filtered by tags."""
    documents_ids = get_document_by_tag(conn, tags)
    if not documents_ids:
        print("no documents")
        return 0
    for doc_id in documents_ids:
        doc = get_document(conn, doc_id)
        doc_tags = get_document_tags(conn, doc_id)
        size = format_size(doc["size_bytes"])
        tag_text = f"  [{', '.join(doc_tags)}]" if doc_tags else ""
        print(
            f"#{doc['id']:>4} {doc['original_name']:<30} "
            f"{size:>10} {doc['status']:<10}{tag_text}"
        )
    return 0

def print_tags(conn: sqlite3.Connection, document_id: int) -> None:
    """Print the current tags of a document."""
    tags = get_document_tags(conn, document_id)
    print(f"#{document_id} [{', '.join(tags)}]" if tags else f"#{document_id} no tags")

def cmd_tag(conn: sqlite3.Connection, document_id: int, names: list[str]) -> int:
    """Add tags to a document and print its tags; return 1 if it does not exist."""
    if get_document(conn, document_id) is None:
        print(f"error: no document #{document_id}", file=sys.stderr)
        return 1
    names = [normalize_tag(name) for name in names]
    for name in names:
        add_tag(conn, document_id, name)
    print_tags(conn, document_id)
    return 0

def cmd_untag(conn: sqlite3.Connection, document_id: int, names: list[str]) -> int:
    """Remove tags from a document and print its tags; return 1 if it does not exist."""
    if get_document(conn, document_id) is None:
        print(f"error: no document #{document_id}", file=sys.stderr)
        return 1
    names = [normalize_tag(name) for name in names]
    for name in names:
        remove_tag(conn, document_id, name)
    print_tags(conn, document_id)
    return 0

def cmd_delete(conn: sqlite3.Connection, document_ids: list[int], assume_yes: bool) -> int:
    """Delete documents after confirmation; return 1 if any of them does not exist."""
    exit_code = 0
    for doc_id in document_ids:
        doc = get_document(conn, doc_id)
        if doc is None:
            print(f"error: no document #{doc_id}", file=sys.stderr)
            exit_code = 1
            continue
        if not assume_yes:
            answer = input(f"delete document #{doc_id} [{doc['original_name']}]? [y/N] ")
            if answer.strip().lower() != "y":
                print("skipped")
                continue
        delete_document(conn, doc_id)
        print(f"deleted document #{doc_id} [{doc['original_name']}]")
    return exit_code

def cmd_index(conn: sqlite3.Connection, rebuild: bool = False) -> int:
    """Index pending documents or rebuild the index and report failures."""
    condition = "" if rebuild else "WHERE status IN ('queued', 'processing')"
    pending = conn.execute(
        f"SELECT id FROM documents {condition} ORDER BY id"
    ).fetchall()
    if not pending:
        print("no documents to reindex" if rebuild else "no documents to index")
        return 0
    action = "reindexing" if rebuild else "indexing"
    print(f"{action} {len(pending)} documents...", flush=True)

    try:
        from esper.embedding import Embedder
        embedder = Embedder()
    except Exception as exc:
        print(f"error: could not load embedding model: {exc}", file=sys.stderr)
        return 1

    try:
        operation = reindex_all if rebuild else index_queued
        indexed, failed = operation(conn, embedder)
    except sqlite3.DatabaseError as exc:
        print(f"error: could not update search index: {exc}", file=sys.stderr)
        return 1
    print(f"indexed {indexed} documents")
    
    if failed:
        for row in pending:
            doc = get_document(conn, row["id"])
            if doc["status"] == "error":
                print(f"error: #{doc['id']} {doc['original_name']}: {doc['error']}", file=sys.stderr)
    for row in pending:
        doc = get_document(conn, row["id"])
        if doc["status"] == "indexed" and doc["extraction_warning"]:
            print(f"warning: #{doc['id']} {doc['original_name']}: {doc['extraction_warning']}", file=sys.stderr)
    
    return 1 if failed else 0


def cmd_search(
    conn: sqlite3.Connection, query: str, tags: list[str], limit: int, mode: str,
    json_output: bool = False,
) -> int:
    """Load a model only when needed and display source passages for each document."""
    validate_search(query, limit, mode)
    embedder = None
    if mode != "keyword" and searchable_chunk_count(conn, tags):
        try:
            from esper.embedding import Embedder
            embedder = Embedder()
        except Exception as exc:
            print(f"error: could not load embedding model: {exc}", file=sys.stderr)
            return 1
    try:
        hits = search_documents(conn, query, embedder, tags=tags, limit=limit, mode=mode)
    except (sqlite3.DatabaseError, RuntimeError) as exc:
        print(f"error: could not search index: {exc}", file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps([asdict(hit) for hit in hits], ensure_ascii=False))
    elif not hits:
        print("no results")
    else:
        for hit in hits:
            tag_text = f"  [{', '.join(hit.tags)}]" if hit.tags else ""
            print(f"#{hit.document_id:>4} {hit.name}  score={hit.score:.6f}{tag_text}")
            for match in hit.matches:
                passage = " ".join(match.text.split())
                if len(passage) > 240:
                    passage = passage[:239].rstrip() + "…"
                location = f"page {match.page}, " if match.page is not None else ""
                source = {"ocr": "OCR, ", "caption": "generated description, "}.get(match.source, "")
                print(f"  [{match.via}, {location}{source}passage {match.position + 1}] {passage}")
    return 0
