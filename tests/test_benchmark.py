"""Benchmark correctness, reproducibility barriers and isolation without weights."""

from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from esper.benchmark import compare_reports, load_benchmark, ranking_metrics, run_benchmark


class Model:
    model_name = "benchmark-test"
    dimensions = 8
    batch_size = 2

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, texts):
        values = np.zeros((len(texts), 8), dtype=np.float32)
        for i, text in enumerate(texts):
            values[i, int("gatto" in text)] = 1
        return values

    def embed_query(self, text):
        return self.embed([text])[0]


@pytest.fixture
def manifest(tmp_path):
    data = {"schema_version": 1, "name": "test", "version": "1", "description": "Temporary test corpus",
            "documents": [{"key": "cat", "format": "txt", "text": "gatto sul divano", "tags": ["casa"]},
                          {"key": "bill", "format": "md", "text": "bolletta energia"}],
            "queries": [{"id": "q1", "query": "gatto", "relevant_documents": ["cat"], "slices": ["text"]},
                        {"id": "q2", "query": "bolletta", "relevant_documents": ["bill"]},
                        {"id": "q3", "query": "marziano", "relevant_documents": []}]}
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data))
    return path


def test_metrics_hand_calculated_and_unanswerable_separated():
    result = ranking_metrics(["wrong", "b", "a"], ["a", "b"])
    assert result["recall@1"] == 0
    assert result["recall@5"] == 1
    assert result["hit@5"] == 1
    assert result["mrr@10"] == .5
    assert result["ndcg@5"] == pytest.approx((1 / math.log2(3) + .5) / (1 + 1 / math.log2(3)))
    assert ranking_metrics([], ["a"])["mrr@10"] == 0
    assert ranking_metrics([], []) == {"empty_result": 1}
    assert ranking_metrics(["a"], []) == {"empty_result": 0}


def test_fingerprint_tracks_asset_bytes_and_labels(manifest):
    data = json.loads(manifest.read_text())
    asset = manifest.parent / "cat.txt"
    asset.write_text(data["documents"][0].pop("text"))
    data["documents"][0]["path"] = "cat.txt"
    manifest.write_text(json.dumps(data))
    first = load_benchmark(manifest)["fingerprint"]
    asset.write_text("gatto nuovo testo")
    second = load_benchmark(manifest)["fingerprint"]
    assert first != second
    data["queries"][0]["relevant_documents"] = ["bill"]
    manifest.write_text(json.dumps(data))
    assert second != load_benchmark(manifest)["fingerprint"]


def test_asset_changed_during_model_loading_is_rejected(manifest):
    data = json.loads(manifest.read_text())
    asset = manifest.parent / "cat.txt"
    asset.write_text(data["documents"][0].pop("text"))
    data["documents"][0]["path"] = "cat.txt"
    manifest.write_text(json.dumps(data))
    validated = load_benchmark(manifest)

    def factory():
        asset.write_text("Changed during loading")
        return Model()

    with pytest.raises(ValueError, match="changed after validation"):
        run_benchmark(validated, factory, repeats=1)


@pytest.mark.parametrize("problem", ["duplicate", "unknown", "tag", "traversal", "duplicate_query", "bad_page", "missing_relevance"])
def test_invalid_manifests_fail_before_model_load(manifest, problem):
    data = json.loads(manifest.read_text())
    if problem == "duplicate":
        data["documents"][1]["text"] = data["documents"][0]["text"]
    elif problem == "unknown":
        data["queries"][0]["relevant_documents"] = ["unknown"]
    elif problem == "tag":
        data["queries"][0]["tags"] = ["missing"]
    elif problem == "traversal":
        del data["documents"][0]["text"]
        data["documents"][0]["path"] = "../outside.txt"
    elif problem == "duplicate_query":
        data["queries"][1]["id"] = "q1"
    elif problem == "bad_page":
        data["queries"][0]["relevant_pages"] = {"cat": [0]}
    else:
        del data["queries"][0]["relevant_documents"]
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_benchmark(manifest)


def test_real_pipeline_report_and_comparison(manifest, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    sentinel = tmp_path / "data"
    sentinel.mkdir()
    (sentinel / "esper.db").write_bytes(b"Do not touch")
    report = run_benchmark(load_benchmark(manifest), Model, repeats=2)
    assert (sentinel / "esper.db").read_bytes() == b"Do not touch"
    assert report["build"]["documents"] == 2
    assert report["build"]["chunks"] == 2
    assert report["model"]["settings"]["dimensions"] == 8
    keyword = report["results"]["keyword"]
    assert keyword["metrics"]["mrr@10"] == 1
    assert keyword["answerable"] == 2 and keyword["unanswerable"] == 1
    assert keyword["unanswerable_empty_rate"] == 1
    assert keyword["latency"]["samples"] == 6
    assert all(row["stable_ranking"] for row in keyword["queries"])
    json.dumps(report)
    comparison = compare_reports(report, deepcopy(report))
    assert comparison["results"]["hybrid"]["metric_delta"]["recall@5"] == 0
    changed = deepcopy(report)
    changed["dataset"]["fingerprint"] = "different"
    with pytest.raises(ValueError, match="fingerprints"):
        compare_reports(report, changed)
    changed = deepcopy(report)
    changed["protocol"]["limit"] = 5
    with pytest.raises(ValueError, match="protocol"):
        compare_reports(report, changed)


def test_frozen_text_benchmark_validates():
    path = Path(__file__).resolve().parent.parent / "evaluation/benchmark-v1.json"
    data = load_benchmark(path)
    assert len(data["documents"]) == 45
    assert len(data["queries"]) == 85
    assert sum(not case["relevant_documents"] for case in data["queries"]) == 3


def test_future_dimension_changes_build_separate_indexes_and_compare(manifest):
    class SmallerModel(Model):
        model_name = "future-test-adapter"
        dimensions = 4

        def embed(self, texts):
            return super().embed(texts)[:, :4].copy()

    before = run_benchmark(load_benchmark(manifest), Model, repeats=1, modes=("semantic",))
    after = run_benchmark(load_benchmark(manifest), SmallerModel, repeats=1, modes=("semantic",))
    assert before["model"]["settings"]["dimensions"] == 8
    assert after["model"]["settings"]["dimensions"] == 4
    assert compare_reports(before, after)["results"]["semantic"]["metric_delta"]["mrr@10"] == 0


def test_pdf_manifest_uses_real_files_and_evaluates_pages():
    path = Path(__file__).resolve().parent.parent / "evaluation/pdf-v1.json"
    data = load_benchmark(path)
    report = run_benchmark(data, Model, repeats=1, modes=("keyword",))
    assert report["build"]["documents"] == 10
    assert report["build"]["chunks"] == 29
    assert "page_hit@5" in report["results"]["keyword"]["metrics"]
    mixed = next(doc for doc in report["documents"] if doc["key"] == "workshop_mixed")
    assert mixed["page_count"] == 3 and "2" in mixed["extraction_warning"]


def test_benchmark_cli_rejects_overwrite_and_invalid_repeats_before_inference(manifest, tmp_path, capsys):
    from scripts.benchmark import main

    output = tmp_path / "report.json"
    output.write_text("preserve")
    assert main(["run", "--dataset", str(manifest), "--output", str(output)]) == 1
    assert output.read_text() == "preserve"
    assert "already exists" in capsys.readouterr().err
    assert main(["run", "--dataset", str(manifest), "--output", str(tmp_path / 'new.json'), "--repeats", "0"]) == 1
    assert "positive" in capsys.readouterr().err
