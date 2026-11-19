"""Tests for esper.cli: argument parsing, commands, output and exit codes."""

from functools import partial
import subprocess
import sys
import sqlite3
from types import ModuleType

import numpy as np
import pytest

from esper import cli
from esper.config import EMBEDDING_DIMENSIONS
from esper.db import connect
from esper.indexing import index_queued, reindex_all
from esper.storage import delete_document, import_file


@pytest.fixture
def db_path(tmp_path, files_dir, monkeypatch):
    """Point the CLI at a temporary database and archive, so tests never touch data/."""
    db_path = tmp_path / "esper.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)
    # files_dir defaults are bound when storage.py is loaded, so patch the functions the CLI calls
    monkeypatch.setattr(cli, "import_file", partial(import_file, files_dir=files_dir))
    monkeypatch.setattr(cli, "delete_document", partial(delete_document, files_dir=files_dir))
    monkeypatch.setattr(cli, "index_queued", partial(index_queued, files_dir=files_dir))
    monkeypatch.setattr(cli, "reindex_all", partial(reindex_all, files_dir=files_dir))
    return db_path


@pytest.fixture
def run(db_path, capsys):
    """Return a function that runs the CLI and returns (exit code, stdout, stderr)."""

    def _run(*argv):
        exit_code = cli.main(list(argv))
        out, err = capsys.readouterr()
        return exit_code, out, err

    return _run


@pytest.fixture
def two_docs(run, make_file):
    """Import a.txt as #1 and b.md as #2."""
    run("import", str(make_file("a.txt", "Hello world!")), str(make_file("b.md", "Hello mondo!")))


def answer(monkeypatch, text):
    """Make input() return the given text, as if the user had typed it."""
    monkeypatch.setattr("builtins.input", lambda prompt: text)


def count_documents(db_path):
    """Return the number of documents in the database."""
    conn = connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    finally:
        conn.close()


def test_pdf_cli_index_warning_and_search_page_json(run, tmp_path, embedding_module):
    import json
    import pymupdf

    path = tmp_path / "mixed.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.new_page().insert_text((70, 110), "caldaia 2400 euro")
        pdf.save(path)
    assert run("import", str(path))[0] == 0
    code, out, err = run("index")
    assert code == 0 and "indexed 1 documents" in out
    assert "warning:" in err and "Pagine senza testo estraibile: 1" in err
    code, out, err = run("search", "caldaia", "--mode", "keyword")
    assert code == 0 and "page 2" in out
    code, out, err = run("search", "caldaia", "--mode", "keyword", "--json")
    assert code == 0 and json.loads(out)[0]["matches"][0]["page"] == 2


# --- Argument parsing --------------------------------------------------------------


def test_missing_command_is_an_error(run):
    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 2


def test_unknown_command_is_an_error(run):
    with pytest.raises(SystemExit) as exc:
        run("explode")
    assert exc.value.code == 2


@pytest.mark.parametrize("command", ["tag", "untag", "delete"])
def test_document_id_must_be_an_integer(run, command):
    with pytest.raises(SystemExit) as exc:
        run(command, "abc", "x")
    assert exc.value.code == 2


def test_first_run_creates_the_database(run, db_path):
    run("list")
    assert db_path.is_file()


# --- import ------------------------------------------------------------------------


def test_import_new_file(run, make_file, files_dir):
    exit_code, out, _ = run("import", str(make_file("a.txt", "Hello world!")))
    assert exit_code == 0
    assert out == "imported #1 a.txt\n"
    assert len(list(files_dir.iterdir())) == 1


def test_import_duplicate(run, make_file, db_path):
    run("import", str(make_file("a.txt", "Hello world!")))
    exit_code, out, _ = run("import", str(make_file("copy.md", "Hello world!")))
    assert exit_code == 0
    assert out == "already present as #1 copy.md\n"
    assert count_documents(db_path) == 1


def test_import_missing_file_does_not_stop_the_others(run, make_file, tmp_path, db_path):
    missing = tmp_path / "missing.txt"
    exit_code, out, err = run("import", str(missing), str(make_file("a.txt", "Hello world!")))
    assert exit_code == 1
    assert err == f"error: {missing} is not a file\n"
    assert out == "imported #1 a.txt\n"
    assert count_documents(db_path) == 1


# --- list --------------------------------------------------------------------------


def test_list_empty_archive(run):
    assert run("list") == (0, "no documents\n", "")


def test_list_shows_name_size_status_and_tags(run, two_docs):
    run("tag", "1", "lavoro", "casa")
    exit_code, out, _ = run("list")
    assert exit_code == 0
    first, second = out.splitlines()
    assert first.split() == ["#", "1", "a.txt", "12", "B", "queued", "[casa,", "lavoro]"]
    assert second.split() == ["#", "2", "b.md", "12", "B", "queued"]


def test_list_filters_by_tag(run, two_docs):
    run("tag", "1", "lavoro", "casa")
    run("tag", "2", "lavoro")
    _, out, _ = run("list", "--tag", "LAVORO")
    assert len(out.splitlines()) == 2
    _, out, _ = run("list", "--tag", "lavoro", "--tag", "casa")
    assert len(out.splitlines()) == 1 and "a.txt" in out


def test_list_unknown_tag(run, two_docs):
    assert run("list", "--tag", "nonexistent") == (0, "no documents\n", "")


def test_list_empty_tag_is_an_error(run):
    assert run("list", "--tag", "  ") == (1, "", "error: Tag name cannot be empty\n")


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 B"),
        (833, "833 B"),
        (1023, "1023 B"),
        (1024, "1.0 KiB"),
        (1536, "1.5 KiB"),
        (1024**2, "1.0 MiB"),
        (int(2.5 * 1024**3), "2.5 GiB"),
        (3 * 1024**4, "3072.0 GiB"),
    ],
)
def test_format_size(size, expected):
    assert cli.format_size(size) == expected


# --- tag / untag -------------------------------------------------------------------


def test_tag_normalizes_and_prints_current_tags(run, two_docs):
    assert run("tag", "1", "Lavoro", "contratti casa") == (0, "#1 [contratti-casa, lavoro]\n", "")


def test_tag_missing_document(run):
    assert run("tag", "99", "x") == (1, "", "error: no document #99\n")


def test_tag_with_an_empty_name_adds_nothing(run, two_docs):
    exit_code, _, err = run("tag", "1", "ok", "  ")
    assert exit_code == 1
    assert err == "error: Tag name cannot be empty\n"
    assert run("untag", "1", "never-added")[1] == "#1 no tags\n"


def test_untag_removes_and_ignores_missing_tags(run, two_docs):
    run("tag", "1", "lavoro", "casa")
    assert run("untag", "1", "LAVORO", "never-added") == (0, "#1 [casa]\n", "")


def test_untag_last_tag(run, two_docs):
    run("tag", "1", "lavoro")
    assert run("untag", "1", "lavoro") == (0, "#1 no tags\n", "")


def test_untag_missing_document(run):
    assert run("untag", "99", "x") == (1, "", "error: no document #99\n")


def test_untag_with_an_empty_name_removes_nothing(run, two_docs):
    run("tag", "1", "lavoro")
    assert run("untag", "1", "lavoro", "  ")[0] == 1
    assert run("tag", "1", "lavoro")[1] == "#1 [lavoro]\n"


# --- delete ------------------------------------------------------------------------


def test_delete_with_yes_flag(run, two_docs, files_dir, db_path, monkeypatch):
    # -y must never ask: a call to input() would fail the test
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("input() was called"))
    exit_code, out, err = run("delete", "1", "-y")
    assert (exit_code, out, err) == (0, "deleted document #1 [a.txt]\n", "")
    assert count_documents(db_path) == 1
    assert len(list(files_dir.iterdir())) == 1


@pytest.mark.parametrize("text", ["y", "Y", " y "])
def test_delete_confirmed(run, two_docs, db_path, monkeypatch, text):
    answer(monkeypatch, text)
    exit_code, out, _ = run("delete", "1")
    assert exit_code == 0
    assert "deleted document #1 [a.txt]" in out
    assert count_documents(db_path) == 1


@pytest.mark.parametrize("text", ["", "n", "yes", "no"])
def test_delete_not_confirmed(run, two_docs, db_path, monkeypatch, text):
    answer(monkeypatch, text)
    assert run("delete", "1") == (0, "skipped\n", "")
    assert count_documents(db_path) == 2


def test_delete_prompt_shows_the_document_name(run, two_docs, monkeypatch):
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "n")
    run("delete", "2")
    assert prompts == ["delete document #2 [b.md]? [y/N] "]


def test_delete_missing_document_does_not_stop_the_others(run, two_docs, db_path):
    exit_code, out, err = run("delete", "99", "1", "-y")
    assert exit_code == 1
    assert err == "error: no document #99\n"
    assert out == "deleted document #1 [a.txt]\n"
    assert count_documents(db_path) == 1


# --- index -------------------------------------------------------------------------


@pytest.fixture
def embedding_module(monkeypatch):
    """Replace the optional model module without importing PyTorch."""
    module = ModuleType("esper.embedding")
    module.instances = []

    class FakeEmbedder:
        def __init__(self):
            self.model_name = "test/model"
            self.dimensions = EMBEDDING_DIMENSIONS
            self.calls = []
            self.queries = []
            module.instances.append(self)

        def count_tokens(self, text):
            return len(text.split())

        def embed(self, texts):
            self.calls.append(list(texts))
            vectors = np.zeros((len(texts), self.dimensions), dtype=np.float32)
            vectors[:, 0] = 1.0
            return vectors

        def embed_query(self, query):
            self.queries.append(query)
            return self.embed([query])[0]

    module.Embedder = FakeEmbedder
    monkeypatch.setitem(sys.modules, "esper.embedding", module)
    return module


def read_document_states(db_path):
    conn = connect(db_path)
    try:
        return [tuple(row) for row in conn.execute(
            "SELECT id, status, error FROM documents ORDER BY id"
        )]
    finally:
        conn.close()


def test_index_help_describes_the_command_without_creating_a_database(run, db_path):
    with pytest.raises(SystemExit) as exc:
        run("index", "--help")
    assert exc.value.code == 0
    assert not db_path.exists()


def test_index_rejects_a_document_id_argument(run):
    with pytest.raises(SystemExit) as exc:
        run("index", "1")
    assert exc.value.code == 2


@pytest.mark.parametrize("status", [None, "indexed", "error"])
def test_index_without_pending_work_does_not_load_a_model(
    run, make_file, db_path, embedding_module, status
):
    if status is not None:
        run("import", str(make_file("old.txt", "Old document.")))
        conn = connect(db_path)
        try:
            with conn:
                conn.execute("UPDATE documents SET status = ?", (status,))
        finally:
            conn.close()

    assert run("index") == (0, "no documents to index\n", "")
    assert embedding_module.instances == []


def test_index_processes_queued_and_interrupted_documents_with_one_model(
    run, two_docs, db_path, embedding_module
):
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE documents SET status = 'processing' WHERE id = 2")
    finally:
        conn.close()

    assert run("index") == (0, "indexing 2 documents...\nindexed 2 documents\n", "")

    assert len(embedding_module.instances) == 1
    assert embedding_module.instances[0].calls == [["Hello world!"], ["Hello mondo!"]]
    assert read_document_states(db_path) == [(1, "indexed", None), (2, "indexed", None)]
    conn = connect(db_path)
    try:
        for table in ("chunks", "chunks_fts", "chunks_vec"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 2
    finally:
        conn.close()
    assert run("index") == (0, "no documents to index\n", "")
    assert len(embedding_module.instances) == 1


def test_index_reports_only_new_failures_and_continues_with_other_documents(
    run, make_file, db_path, embedding_module
):
    run(
        "import",
        str(make_file("bad.bin", "Unsupported document.")),
        str(make_file("good.txt", "Good document.")),
        str(make_file("old.txt", "Previous failure.")),
    )
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE documents SET status = 'error', error = 'Old failure' WHERE id = 3")
    finally:
        conn.close()

    assert run("index") == (
        1,
        "indexing 2 documents...\nindexed 1 documents\n",
        "error: #1 bad.bin: UnsupportedFormatError: application/octet-stream\n",
    )

    assert read_document_states(db_path) == [
        (1, "error", "UnsupportedFormatError: application/octet-stream"),
        (2, "indexed", None),
        (3, "error", "Old failure"),
    ]
    assert embedding_module.instances[0].calls == [["Good document."]]
    assert run("index") == (0, "no documents to index\n", "")
    assert len(embedding_module.instances) == 1


@pytest.mark.parametrize("failure", ["import", "initialization"])
def test_index_reports_model_loading_failure_without_changing_document_states(
    run, two_docs, db_path, embedding_module, monkeypatch, failure
):
    if failure == "import":
        monkeypatch.setitem(sys.modules, "esper.embedding", None)
    else:
        def fail_to_load():
            raise RuntimeError("Model unavailable")

        embedding_module.Embedder = fail_to_load
    before = read_document_states(db_path)

    exit_code, out, err = run("index")

    assert exit_code == 1
    assert out == "indexing 2 documents...\n"
    assert err.startswith("error: could not load embedding model:")
    assert "Traceback" not in err
    assert read_document_states(db_path) == before


def test_index_returns_failure_when_all_documents_are_unsupported(run, make_file, embedding_module):
    run("import", str(make_file("bad.bin", "Unsupported PDF.")))

    assert run("index") == (
        1,
        "indexing 1 documents...\nindexed 0 documents\n",
        "error: #1 bad.bin: UnsupportedFormatError: application/octet-stream\n",
    )
    assert len(embedding_module.instances) == 1
    assert embedding_module.instances[0].calls == []


def test_unrelated_commands_and_empty_index_do_not_import_the_embedding_module(tmp_path):
    script = """
import sys
from pathlib import Path
from esper import cli

cli.DB_PATH = Path(sys.argv[1])
assert cli.main(['list']) == 0
assert cli.main(['index']) == 0
assert cli.main(['reindex']) == 0
assert cli.main(['search', 'hello']) == 0
assert cli.main(['search', 'hello', '--mode', 'keyword']) == 0
assert 'esper.embedding' not in sys.modules
assert 'torch' not in sys.modules
assert 'PySide6' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "test.db")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


# --- reindex -----------------------------------------------------------------------


def test_empty_reindex_does_not_load_a_model(run, embedding_module):
    assert run("reindex") == (0, "no documents to reindex\n", "")
    assert embedding_module.instances == []


def test_reindex_help_does_not_create_a_database(run, db_path):
    with pytest.raises(SystemExit) as exc:
        run("reindex", "--help")
    assert exc.value.code == 0
    assert not db_path.exists()


def test_reindex_rejects_document_arguments(run):
    with pytest.raises(SystemExit) as exc:
        run("reindex", "1")
    assert exc.value.code == 2


def test_reindex_retries_old_errors_and_reprocesses_indexed_documents(run, two_docs, db_path, embedding_module):
    assert run("index")[0] == 0
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE documents SET status = 'error', error = 'Old error' WHERE id = 2")
    finally:
        conn.close()

    assert run("reindex") == (0, "reindexing 2 documents...\nindexed 2 documents\n", "")

    assert len(embedding_module.instances) == 2
    assert embedding_module.instances[-1].calls == [["Hello world!"], ["Hello mondo!"]]
    assert read_document_states(db_path) == [(1, "indexed", None), (2, "indexed", None)]


@pytest.mark.parametrize("metadata", ["unknown", "incompatible"])
def test_index_reports_settings_problem_and_explicit_reindex_repairs_it(
    run, two_docs, db_path, embedding_module, metadata
):
    assert run("index")[0] == 0
    conn = connect(db_path)
    try:
        with conn:
            if metadata == "unknown":
                conn.execute("DELETE FROM index_settings")
            else:
                conn.execute("UPDATE index_settings SET chunk_max_tokens = 300")
            conn.execute("UPDATE documents SET status = 'processing' WHERE id = 2")
    finally:
        conn.close()
    before = read_document_states(db_path)

    code, out, error = run("index")

    assert code == 1
    assert out == "indexing 1 documents...\n"
    assert "esper reindex" in error
    assert "Traceback" not in error
    assert embedding_module.instances[-1].calls == []
    assert read_document_states(db_path) == before
    assert run("reindex")[0] == 0


def test_reindex_load_failure_preserves_existing_index(run, two_docs, db_path, embedding_module):
    assert run("index")[0] == 0
    conn = connect(db_path)
    try:
        before = [tuple(row) for row in conn.execute("SELECT rowid, embedding FROM chunks_vec")]
    finally:
        conn.close()
    states = read_document_states(db_path)

    def fail_to_load():
        raise RuntimeError("Model unavailable")

    embedding_module.Embedder = fail_to_load
    code, out, error = run("reindex")
    assert code == 1
    assert out == "reindexing 2 documents...\n"
    assert "could not load embedding model" in error
    assert read_document_states(db_path) == states
    conn = connect(db_path)
    try:
        assert [tuple(row) for row in conn.execute("SELECT rowid, embedding FROM chunks_vec")] == before
    finally:
        conn.close()


def test_reindex_reports_current_document_failures(run, make_file, embedding_module):
    run("import", str(make_file("bad.bin", "Unsupported PDF.")))
    assert run("reindex") == (
        1,
        "reindexing 1 documents...\nindexed 0 documents\n",
        "error: #1 bad.bin: UnsupportedFormatError: application/octet-stream\n",
    )


def test_reindex_interrupt_has_actionable_message_and_index_resumes(run, two_docs, db_path, embedding_module):
    assert run("index")[0] == 0
    base = embedding_module.Embedder

    class InterruptedEmbedder(base):
        def embed(self, texts):
            if texts == ["Hello mondo!"]:
                raise KeyboardInterrupt
            return super().embed(texts)

    embedding_module.Embedder = InterruptedEmbedder
    code, out, error = run("reindex")
    assert code == 130
    assert out == "reindexing 2 documents...\n"
    assert "esper index" in error
    assert read_document_states(db_path) == [(1, "indexed", None), (2, "processing", None)]
    embedding_module.Embedder = base
    assert run("index") == (0, "indexing 1 documents...\nindexed 1 documents\n", "")
    assert embedding_module.instances[-1].calls == [["Hello mondo!"]]


def test_reindex_database_error_is_reported_without_a_traceback(run, two_docs, embedding_module, monkeypatch):
    def fail_reset(*args):
        raise sqlite3.OperationalError("Reset failed")

    monkeypatch.setattr(cli, "reindex_all", fail_reset)
    code, out, error = run("reindex")
    assert code == 1
    assert out == "reindexing 2 documents...\n"
    assert error == "error: could not update search index: Reset failed\n"


# --- search ------------------------------------------------------------------------


def test_search_help_does_not_create_database(run, db_path):
    with pytest.raises(SystemExit) as exc:
        run("search", "--help")
    assert exc.value.code == 0
    assert not db_path.exists()


@pytest.mark.parametrize("arguments", [(), ("hello", "--mode", "invalid"), ("hello", "--limit", "many")])
def test_search_invalid_arguments_are_parser_errors(run, arguments):
    with pytest.raises(SystemExit) as exc:
        run("search", *arguments)
    assert exc.value.code == 2


@pytest.mark.parametrize("arguments", [("",), ("   ",), ("hello", "--limit", "0"), ("hello", "--tag", " ")])
def test_search_invalid_requests_do_not_load_model(run, embedding_module, arguments):
    code, out, error = run("search", *arguments)
    assert code == 1
    assert out == ""
    assert error.startswith("error:")
    assert embedding_module.instances == []


def test_search_queued_documents_returns_no_results_without_loading_model(run, two_docs, embedding_module):
    assert run("search", "hello") == (0, "no results\n", "")
    assert embedding_module.instances == []


def test_search_prints_ranked_source_passages_and_loads_one_model(run, two_docs, embedding_module):
    assert run("index")[0] == 0
    run("tag", "1", "notes")

    code, out, error = run("search", "hello", "--limit", "1")

    assert code == 0 and error == ""
    assert "#   1 a.txt" in out
    assert "[notes]" in out
    assert "[both, passage 1] Hello world!" in out
    assert "b.md" not in out
    assert len(embedding_module.instances) == 2
    assert embedding_module.instances[-1].queries == ["hello"]


def test_search_json_contains_full_passages_and_metadata(run, two_docs, embedding_module):
    import json
    run("index")
    code, out, error = run("search", "hello", "--json")
    assert code == 0 and error == ""
    results = json.loads(out)
    assert [result["document_id"] for result in results] == [1, 2]
    assert results[0]["mime_type"] == "text/plain"
    assert results[0]["matches"][0]["text"] == "Hello world!"
    assert results[0]["matches"][0]["distance"] == pytest.approx(0)
    assert results[0]["matches"][0]["via"] == "both"
    assert isinstance(results[0]["score"], float)


def test_search_keyword_mode_does_not_import_model(run, two_docs, embedding_module, monkeypatch):
    run("index")
    monkeypatch.setitem(sys.modules, "esper.embedding", None)
    code, out, error = run("search", "mondo", "--mode", "keyword")
    assert code == 0 and error == ""
    assert "b.md" in out and "a.txt" not in out
    assert "[keyword, passage 1] Hello mondo!" in out


def test_search_tag_filters_and_unknown_tags_skip_model_loading(run, two_docs, embedding_module):
    run("index")
    run("tag", "2", "Lavoro", "Fatture casa")
    code, out, error = run("search", "hello", "--tag", "lavoro", "--tag", "fatture casa")
    assert code == 0 and error == ""
    assert "b.md" in out and "a.txt" not in out
    count = len(embedding_module.instances)
    assert run("search", "hello", "--tag", "missing") == (0, "no results\n", "")
    assert len(embedding_module.instances) == count


def test_search_empty_json_result_is_an_array(run, embedding_module):
    assert run("search", "hello", "--json") == (0, "[]\n", "")
    assert embedding_module.instances == []


def test_search_reports_model_loading_failure(run, two_docs, embedding_module):
    run("index")

    def fail():
        raise RuntimeError("Model unavailable")

    embedding_module.Embedder = fail
    code, out, error = run("search", "hello")
    assert code == 1 and out == ""
    assert error == "error: could not load embedding model: Model unavailable\n"


def test_search_reports_inference_failure_without_changing_document_states(run, two_docs, db_path, embedding_module):
    run("index")
    before = read_document_states(db_path)
    base = embedding_module.Embedder

    class BrokenQueryEmbedder(base):
        def embed_query(self, query):
            raise RuntimeError("Inference failed")

    embedding_module.Embedder = BrokenQueryEmbedder
    code, out, error = run("search", "hello")
    assert code == 1 and out == ""
    assert error == "error: could not search index: Inference failed\n"
    assert read_document_states(db_path) == before


def test_search_unknown_settings_requires_reindex(run, two_docs, db_path, embedding_module):
    run("index")
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM index_settings")
    finally:
        conn.close()
    code, out, error = run("search", "hello")
    assert code == 1 and out == ""
    assert error == "error: Existing index settings are unknown; run 'esper reindex'\n"


def test_search_ctrl_c_returns_130(run, two_docs, embedding_module):
    run("index")
    base = embedding_module.Embedder

    class InterruptedQueryEmbedder(base):
        def embed_query(self, query):
            raise KeyboardInterrupt

    embedding_module.Embedder = InterruptedQueryEmbedder
    assert run("search", "hello") == (130, "", "interrupted\n")


def test_search_displays_part_of_a_long_unbroken_passage_and_keeps_full_json(run, make_file, embedding_module):
    import json
    text = "a" * 300
    run("import", str(make_file("long.txt", text)))
    assert run("index")[0] == 0
    code, output, error = run("search", "description", "--mode", "semantic")
    assert code == 0 and error == ""
    assert output.splitlines()[1] == "  [semantic, passage 1] " + "a" * 239 + "…"
    code, output, error = run("search", "description", "--mode", "semantic", "--json")
    assert code == 0 and error == ""
    assert json.loads(output)[0]["matches"][0]["text"] == text


def test_desktop_help_does_not_open_archive_or_import_qt(run, db_path):
    with pytest.raises(SystemExit) as exc:
        run("desktop", "--help")
    assert exc.value.code == 0
    assert not db_path.exists()


def test_desktop_uses_explicit_archive_without_opening_default_database(run, db_path, tmp_path, monkeypatch):
    module = ModuleType("esper.desktop.app")
    paths = []
    module.run = lambda data_dir: paths.append(data_dir) or 0
    monkeypatch.setitem(sys.modules, "esper.desktop.app", module)
    chosen = tmp_path / "separate-archive"
    assert run("desktop", "--data-dir", str(chosen)) == (0, "", "")
    assert paths == [chosen]
    assert not db_path.exists()
