"""Check retrieval metrics and fixture validation without loading a model."""

import json
from types import SimpleNamespace

import pytest

from esper import evaluation
from esper.evaluation import EvaluationCase, evaluate_search, recall_at_k
from scripts.evaluate_search import DEFAULT_DATASET, load_dataset


def test_recall_measures_fraction_of_all_relevant_documents():
    assert recall_at_k([3, 8, 7], [7, 8], 1) == 0
    assert recall_at_k([3, 8, 7], [7, 8], 2) == 0.5
    assert recall_at_k([3, 8, 7], [7, 8], 5) == 1
    assert recall_at_k([8, 8], [7, 8, 8], 5) == 0.5
    assert recall_at_k([], [7], 10) == 0


@pytest.mark.parametrize(("relevant", "k"), [([], 5), ([1], 0), ([1], -1)])
def test_invalid_metric_requests_fail_explicitly(relevant, k):
    with pytest.raises(ValueError):
        recall_at_k([1], relevant, k)


def test_evaluation_averages_queries_and_preserves_labels_and_filters(conn, monkeypatch):
    calls = []

    def search(conn, query, embedder, **options):
        calls.append((query, options))
        ids = [2, 1] if query == "first" else [4]
        return [SimpleNamespace(document_id=document_id) for document_id in ids]

    monkeypatch.setattr(evaluation, "search_documents", search)
    report = evaluate_search(conn, None, [
        EvaluationCase("first", (1, 2), ("home",)),
        EvaluationCase("second", (3,)),
    ], mode="keyword")
    assert report.query_count == 2
    assert report.recall_at_1 == 0.25
    assert report.recall_at_5 == report.recall_at_10 == 0.5
    assert report.queries[0].retrieved_document_ids == (2, 1)
    assert calls == [
        ("first", {"tags": ("home",), "limit": 10, "mode": "keyword"}),
        ("second", {"tags": (), "limit": 10, "mode": "keyword"}),
    ]


def test_empty_evaluation_is_rejected(conn):
    with pytest.raises(ValueError, match="queries"):
        evaluate_search(conn, None, [])


def test_development_fixture_has_40_labelled_queries_and_20_unique_documents():
    data = load_dataset(DEFAULT_DATASET)
    assert len(data["documents"]) == 20
    assert len(data["queries"]) == 40
    assert any(len(case["relevant_documents"]) > 1 for case in data["queries"])


@pytest.mark.parametrize("problem", ["empty", "unknown_label", "duplicate_key", "duplicate_text", "excluded_by_tag", "blank_query"])
def test_invalid_datasets_are_rejected_before_model_loading(tmp_path, problem):
    data = {
        "documents": [{"key": "first", "text": "Passage", "tags": ["home"]}],
        "queries": [{"query": "description", "relevant_documents": ["first"]}],
    }
    if problem == "empty":
        data["queries"] = []
    elif problem == "unknown_label":
        data["queries"][0]["relevant_documents"] = ["unknown"]
    elif problem == "duplicate_key":
        data["documents"].append({"key": "first", "text": "Different"})
    elif problem == "duplicate_text":
        data["documents"].append({"key": "other", "text": "Passage"})
    elif problem == "excluded_by_tag":
        data["queries"][0]["tags"] = ["work"]
    else:
        data["queries"][0]["query"] = "  "
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(path)
