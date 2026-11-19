"""Run or compare Esper benchmark reports without touching data/."""

import argparse
import json
from pathlib import Path
import sys
import sqlite3

from esper.benchmark import compare_reports, load_benchmark, run_benchmark
from esper.search import SEARCH_MODES


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parent.parent / "evaluation/benchmark-v1.json")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--mode", choices=(*SEARCH_MODES, "all"), default="all")
    run.add_argument("--revision", help="Pin the bge-m3 Hugging Face revision; cached snapshot is used when available")
    compare = sub.add_parser("compare")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            result = compare_reports(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if args.repeats < 1:
                raise ValueError("repeats must be positive")
            if args.output.exists():
                raise ValueError("Output already exists; choose a new filename to preserve previous runs")
            data = load_benchmark(args.dataset)
            def factory():
                from esper.embedding import Embedder
                from esper.config import EMBEDDING_MODEL
                from huggingface_hub import try_to_load_from_cache
                revision = args.revision
                if revision is None:
                    cached = try_to_load_from_cache(EMBEDDING_MODEL, "config.json")
                    if isinstance(cached, str):
                        revision = Path(cached).parent.name
                return Embedder(revision=revision)
            report = run_benchmark(data, factory, modes=SEARCH_MODES if args.mode == "all" else (args.mode,),
                                   repeats=args.repeats, notify=lambda text: print(text, file=sys.stderr, flush=True))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as out:
                json.dump(report, out, ensure_ascii=False, indent=2)
                out.write("\n")
            for mode, result in report["results"].items():
                metrics = result["metrics"]
                print(f"{mode}: recall@5={metrics.get('recall@5', 0):.4f} MRR@10={metrics.get('mrr@10', 0):.4f} "
                      f"nDCG@10={metrics.get('ndcg@10', 0):.4f} median={result['latency']['median_ms']:.1f}ms")
            print(f"Report: {args.output}")
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
