from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.retrieval_evaluation import aggregate_metrics, evaluate_query  # noqa: E402

DATASET_PATH = BACKEND_DIR / "evaluation" / "retrieval_dataset.json"
MODES = ("keyword", "vector", "hybrid")


def post_search(base_url: str, query: str, mode: str, limit: int) -> dict:
    payload = json.dumps({"query": query, "mode": mode, "limit": limit}).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval modes against a small labeled dataset.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI base URL")
    parser.add_argument("--k", type=int, default=5, help="Recall cutoff and API result limit")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--output", help="Optional path for a JSON report")
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    report = {"dataset": str(DATASET_PATH.name), "k": args.k, "modes": {}}

    for mode in args.modes:
        query_rows = []
        details = []
        for case in dataset:
            try:
                response = post_search(args.base_url, case["query"], mode, args.k)
            except HTTPError as error:
                message = error.read().decode("utf-8", errors="replace")
                if mode == "vector":
                    print(f"[skip] vector mode unavailable: {message}", file=sys.stderr)
                    details = []
                    break
                raise
            except (URLError, TimeoutError) as error:
                raise SystemExit(f"Cannot reach API at {args.base_url}: {error}") from error

            effective_mode = response.get("mode")
            expected_effective_mode = "hybrid" if mode == "hybrid" else mode
            if effective_mode != expected_effective_mode:
                details = []
                print(
                    f"[skip] {mode} returned effective mode {effective_mode!r}; "
                    "configure and index embeddings before comparing this mode.",
                    file=sys.stderr,
                )
                break

            results = response.get("results", [])
            metrics = evaluate_query(results, case["gold_phrase"], args.k)
            query_rows.append(metrics)
            details.append({
                "id": case["id"],
                "query": case["query"],
                "effective_mode": response.get("mode"),
                **metrics,
                "first_result": results[0].get("filename") if results else None,
                "gold_rank": next(
                    (rank for rank, item in enumerate(results, 1)
                     if case["gold_phrase"] in item.get("content", "")),
                    None,
                ),
            })

        if details:
            report["modes"][mode] = {
                "metrics": aggregate_metrics(query_rows, args.k),
                "queries": details,
            }
        else:
            report["modes"][mode] = {"available": False, "reason": "No evaluable responses"}

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        print(f"\nSaved report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
