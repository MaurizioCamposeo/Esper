"""Check ranking, literal keyword queries, prefilters and read-only retrieval."""

from dataclasses import replace

import numpy as np
import pytest

from esper import search as search_module
from esper.db import connect, init_schema, recreate_vector_index
from esper.index_settings import get_index_settings, set_index_settings
from esper.indexing import current_index_settings, set_status, write_chunks
from esper.search import (
    keyword_expression, keyword_search, reciprocal_rank_fusion, search_documents,
    searchable_chunk_count, vector_search,
)
from esper.storage import import_file
from esper.tags import add_tag


def vector(first=1.0, second=0.0):
    values = np.zeros(1024, dtype=np.float32)
    values[:2] = first, second
    return values


class QueryEmbedder:
    model_name = "test/model"
    dimensions = 1024

    def __init__(self):
        self.queries = []

    def embed_query(self, query):
        self.queries.append(query)
        return vector()


@pytest.fixture
def embedder(conn):
    model = QueryEmbedder()
    with conn:
        set_index_settings(conn, current_index_settings(model))
    return model


@pytest.fixture
def add_document(conn, make_file, files_dir, embedder):
    def add(name, passages, vectors=None, tags=(), status="indexed"):
        path = make_file(name, name + "\n" + "\n\n".join(passages))
        document_id = import_file(conn, path, files_dir)[0]
        if vectors is None:
            vectors = [vector() for _ in passages]
        write_chunks(conn, document_id, passages, np.asarray(vectors, dtype=np.float32))
        for tag in tags:
            add_tag(conn, document_id, tag)
        if status != "indexed":
            set_status(conn, document_id, status)
        return document_id
    return add


def test_semantic_search_finds_passages_without_query_words(conn, embedder, add_document):
    correct = add_document("heating.txt", ["Sostituito il generatore del riscaldamento."], [vector()])
    add_document("cat.txt", ["Il gatto dorme sul divano."], [vector(0, 1)])
    hits = search_documents(conn, "caldaia nuova", embedder, mode="semantic", limit=1)
    assert [hit.document_id for hit in hits] == [correct]
    assert hits[0].matches[0].via == "semantic"
    assert hits[0].matches[0].distance == pytest.approx(0)
    assert hits[0].matches[0].bm25 is None
    assert embedder.queries == ["caldaia nuova"]


def test_vector_search_has_stable_distance_order_and_accepts_large_limits(conn, add_document):
    first = add_document("first.txt", ["First"], [vector()])
    tied = add_document("tied.txt", ["Tied"], [vector()])
    last = add_document("last.txt", ["Last"], [vector(0, 1)])
    results = vector_search(conn, vector(5, 0), limit=5000)
    assert [result.document_id for result in results] == [first, tied, last]
    assert [result.value for result in results] == pytest.approx([0, 0, 1])


def test_keyword_search_uses_bm25_ranking_and_not_insertion_order(conn, add_document):
    long = add_document("long.txt", ["caldaia " + "divano " * 100])
    short = add_document("short.txt", ["caldaia"])
    results = keyword_search(conn, "caldaia")
    assert [result.document_id for result in results] == [short, long]
    assert results[0].value < results[1].value


@pytest.mark.parametrize("query", ["perché", "PERCHE", '"perche"', "perche: NEAR(*)", "perche OR NOT (gatto)"])
def test_keyword_input_is_literal_and_accents_are_ignored(conn, add_document, query):
    expected = add_document("cat.txt", ["Perché il felino dorme?"])
    assert keyword_search(conn, query)[0].document_id == expected


@pytest.mark.parametrize("query", ['"', "***", "() - :", "🛰️"])
def test_punctuation_only_keyword_queries_do_not_raise_fts_errors(conn, add_document, query):
    add_document("notes.txt", ["Ordinary words"])
    assert search_documents(conn, query, mode="keyword") == []


def test_keyword_operator_injection_cannot_match_unrelated_documents(conn, add_document):
    expected = add_document("cat.txt", ["gatto"])
    add_document("other.txt", ["caldaia"])
    results = keyword_search(conn, 'gatto" OR 1=1 --')
    assert [result.document_id for result in results] == [expected]
    assert keyword_expression('gatto" OR 1=1 --') == '"gatto" OR "OR" OR "1"'


def test_rrf_combines_ranks_instead_of_incomparable_raw_scores():
    fused = reciprocal_rank_fusion([[10, 20], [30, 20]])
    assert [chunk_id for chunk_id, _ in fused] == [20, 10, 30]
    assert fused[0][1] == pytest.approx(2 / 62)
    assert fused[1][1] == pytest.approx(1 / 61)
    assert reciprocal_rank_fusion([[10, 10], []]) == [(10, 1 / 61)]


def test_hybrid_rewards_agreement_and_reports_each_branch(conn, embedder, add_document):
    add_document("semantic.txt", ["Generatore termico"], [vector()])
    agreement = add_document("both.txt", ["caldaia"], [vector(0.9, 0.1)])
    add_document("keyword.txt", ["caldaia " + "unrelated " * 30], [vector(0, 1)])
    hits = search_documents(conn, "caldaia", embedder)
    assert hits[0].document_id == agreement
    assert hits[0].matches[0].via == "both"
    assert hits[0].matches[0].bm25 is not None
    assert hits[0].matches[0].distance is not None


@pytest.mark.parametrize("mode", ["semantic", "keyword", "hybrid"])
def test_all_tag_filters_apply_before_ranking_limits(conn, embedder, add_document, mode):
    add_document("nearest.txt", ["caldaia caldaia"], [vector()], tags=("home",))
    allowed = add_document("allowed.txt", ["caldaia"], [vector(0.2, 0.8)], tags=("Home", "Lavori casa"))
    add_document("wrong.txt", ["caldaia"], [vector()], tags=("lavori-casa",))
    hits = search_documents(
        conn, "caldaia", embedder, tags=("HOME", "Lavori casa", "home"),
        limit=1, candidate_limit=1, mode=mode,
    )
    assert [hit.document_id for hit in hits] == [allowed]
    assert hits[0].tags == ("home", "lavori-casa")


@pytest.mark.parametrize("status", ["queued", "processing", "error"])
def test_unavailable_documents_with_old_chunks_are_excluded(conn, embedder, add_document, status):
    add_document("unavailable.txt", ["caldaia"], status=status)
    available = add_document("available.txt", ["caldaia"])
    assert searchable_chunk_count(conn) == 1
    assert [hit.document_id for hit in search_documents(conn, "caldaia", embedder)] == [available]


def test_long_documents_do_not_crowd_out_distinct_results(conn, embedder, add_document):
    long = add_document("long.txt", [f"Passage {i}" for i in range(70)])
    other = add_document("other.txt", ["Other passage"], [vector(0, 1)])
    hits = search_documents(conn, "meaning", embedder, mode="semantic", limit=2, candidate_limit=2)
    assert [hit.document_id for hit in hits] == [long, other]
    assert len(hits[0].matches) == 3
    assert hits[0].score == hits[0].matches[0].score
    assert len({match.chunk_id for match in hits[0].matches}) == 3


def test_keyword_candidate_pool_expands_until_distinct_documents_are_found(conn, add_document):
    long = add_document("long.txt", ["caldaia" for _ in range(60)])
    other = add_document("other.txt", ["caldaia"])
    hits = search_documents(conn, "caldaia", mode="keyword", limit=2, candidate_limit=1)
    assert [hit.document_id for hit in hits] == [long, other]


@pytest.mark.parametrize("tags", [(), ("missing",)])
def test_empty_eligible_index_does_not_encode_a_query(conn, embedder, tags):
    assert search_documents(conn, "caldaia", embedder, tags=tags) == []
    assert embedder.queries == []


@pytest.mark.parametrize("changes", [
    {"model_name": "other/model"}, {"dimensions": 768},
    {"chunk_max_tokens": 300}, {"chunker_version": 1}, None,
])
def test_incompatible_metadata_is_rejected_without_encoding_or_writing(conn, embedder, add_document, changes):
    add_document("notes.txt", ["caldaia"])
    with conn:
        if changes is None:
            conn.execute("DELETE FROM index_settings")
        else:
            set_index_settings(conn, replace(get_index_settings(conn), **changes))
    before = conn.total_changes
    with pytest.raises(ValueError, match="esper reindex"):
        search_documents(conn, "caldaia", embedder)
    assert embedder.queries == []
    assert conn.total_changes == before


def test_keyword_only_search_does_not_require_model_metadata(conn, add_document):
    expected = add_document("notes.txt", ["caldaia"])
    with conn:
        conn.execute("DELETE FROM index_settings")
    assert search_documents(conn, "caldaia", mode="keyword")[0].document_id == expected
    assert get_index_settings(conn) is None


def test_query_inference_runs_outside_search_snapshot_and_search_is_read_only(conn, embedder, add_document, monkeypatch):
    add_document("notes.txt", ["caldaia"])
    original = embedder.embed_query

    def inspect(query):
        assert not conn.in_transaction
        return original(query)

    monkeypatch.setattr(embedder, "embed_query", inspect)
    changes = conn.total_changes
    assert search_documents(conn, " caldaia ", embedder)
    assert not conn.in_transaction
    assert conn.total_changes == changes
    assert embedder.queries == ["caldaia"]


def test_search_does_not_commit_a_callers_transaction(conn, embedder, add_document):
    add_document("notes.txt", ["caldaia"])
    conn.execute("INSERT INTO tags (name) VALUES ('uncommitted')")
    assert search_documents(conn, "caldaia", embedder)
    assert conn.in_transaction
    conn.rollback()
    assert conn.execute("SELECT 1 FROM tags WHERE name = 'uncommitted'").fetchone() is None


def test_metadata_is_rechecked_after_query_inference(conn, embedder, add_document, monkeypatch):
    add_document("notes.txt", ["caldaia"])

    def change_index(query):
        with conn:
            set_index_settings(conn, replace(get_index_settings(conn), model_name="other/model"))
        return vector()

    monkeypatch.setattr(embedder, "embed_query", change_index)
    with pytest.raises(ValueError, match="esper reindex"):
        search_documents(conn, "caldaia", embedder)


@pytest.mark.parametrize("bad_vector", [np.zeros(1024), np.ones(768), np.ones((1, 1024)), np.full(1024, np.nan), np.full(1024, np.inf)])
def test_invalid_query_vectors_fail_explicitly(conn, add_document, bad_vector):
    add_document("notes.txt", ["caldaia"])
    with pytest.raises(ValueError, match="Query vector"):
        vector_search(conn, bad_vector)


@pytest.mark.parametrize("options", [
    {"query": ""}, {"query": " \n "}, {"limit": 0}, {"limit": -1},
    {"mode": "invalid"}, {"candidate_limit": 0}, {"max_passages": 0},
    {"tags": (" ",)},
])
def test_invalid_requests_fail_even_with_an_empty_archive(conn, embedder, options):
    arguments = {"query": "caldaia", **options}
    with pytest.raises(ValueError):
        search_documents(conn, embedder=embedder, **arguments)
    assert embedder.queries == []


def test_query_model_is_required_when_semantic_search_has_candidates(conn, add_document):
    add_document("notes.txt", ["caldaia"])
    with pytest.raises(ValueError, match="embedding model is required"):
        search_documents(conn, "caldaia")


def test_search_uses_the_loaded_models_dimensions_after_a_rebuild(conn, embedder, add_document, monkeypatch):
    model = QueryEmbedder()
    model.model_name = "future/model"
    model.dimensions = 768
    values = np.zeros(768, dtype=np.float32)
    values[0] = 1
    monkeypatch.setattr(model, "embed_query", lambda query: values)
    with conn:
        recreate_vector_index(conn, 768)
        set_index_settings(conn, current_index_settings(model))
    expected = add_document("notes.txt", ["caldaia"], [values])
    hits = search_documents(conn, "riscaldamento", model, mode="semantic")
    assert hits[0].document_id == expected
    assert hits[0].matches[0].distance == pytest.approx(0)


def test_both_search_branches_and_passages_use_one_snapshot(tmp_path, make_file, files_dir, monkeypatch):
    db_path = tmp_path / "snapshot.db"
    reader = connect(db_path)
    writer = connect(db_path)
    try:
        init_schema(reader)
        model = QueryEmbedder()
        document_id = import_file(reader, make_file("notes.txt", "caldaia"), files_dir)[0]
        write_chunks(reader, document_id, ["caldaia"], np.array([vector()]))
        with reader:
            set_index_settings(reader, current_index_settings(model))
        original = search_module.vector_search

        def delete_between_branches(conn, *args, **kwargs):
            results = original(conn, *args, **kwargs)
            with writer:
                writer.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            return results

        monkeypatch.setattr(search_module, "vector_search", delete_between_branches)
        hits = search_documents(reader, "caldaia", model)
        assert hits[0].document_id == document_id
        assert hits[0].matches[0].via == "both"
        assert hits[0].matches[0].text == "caldaia"
        assert reader.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    finally:
        reader.close()
        writer.close()
