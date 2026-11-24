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


def post_json(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Session-Token"] = token
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def create_evaluation_session(base_url: str) -> str:
    try:
        session = post_json(f"{base_url.rstrip('/')}/session", {})
    except HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Unable to create evaluation session (HTTP {error.code}): {message}") from error
    token = session.get("token")
    if not isinstance(token, str) or not token:
        raise SystemExit("Session endpoint did not return a usable token.")
    return token


def post_search(base_url: str, token: str, query: str, mode: str, limit: int, rerank: bool = False) -> dict:
    return post_json(
        f"{base_url.rstrip('/')}/search",
        {"query": query, "mode": mode, "limit": limit, "rerank": rerank},
        token,
    )


def evaluate_mode(base_url: str, token: str, dataset: list[dict], mode: str, limit: int, rerank: bool = False) -> dict:
    query_rows = []
    details = []
    effective_modes = set()
    reranker_statuses = set()

    for case in dataset:
        try:
            response = post_search(base_url, token, case["query"], mode, limit, rerank)
        except HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            if mode == "vector":
                return {"available": False, "reason": f"Vector mode unavailable (HTTP {error.code}): {message}"}
            raise SystemExit(f"Search failed for {case['id']} in {mode} mode (HTTP {error.code}): {message}") from error
        except (URLError, TimeoutError) as error:
            raise SystemExit(f"Cannot reach API at {base_url}: {error}") from error

        effective_mode = response.get("mode")
        if mode == "hybrid" and effective_mode != "hybrid":
            return {
                "available": False,
                "reason": f"Hybrid requested but API returned {effective_mode!r}; configure embeddings and index vectors.",
            }
        if mode != "hybrid" and effective_mode != mode:
            return {
                "available": False,
                "reason": f"{mode} requested but API returned {effective_mode!r}.",
            }

        results = response.get("results", [])
        metrics = evaluate_query(results, case["gold_phrase"], limit)
        query_rows.append(metrics)
        effective_modes.add(effective_mode)
        reranker_statuses.add(response.get("reranker", "unknown"))
        gold_rank = next(
            (rank for rank, item in enumerate(results, 1)
             if case["gold_phrase"] in item.get("content", "")),
            None,
        )
        details.append({
            "id": case["id"],
            "category": case.get("category", "uncategorized"),
            "query": case["query"],
            "effective_mode": effective_mode,
            **metrics,
            "first_result": results[0].get("filename") if results else None,
            "gold_rank": gold_rank,
        })

    return {
        "available": True,
        "metrics": aggregate_metrics(query_rows, limit),
        "effective_modes": sorted(effective_modes),
        "reranker_statuses": sorted(reranker_statuses),
        "queries": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate authenticated retrieval modes against the labeled demo handbook dataset."
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI base URL")
    parser.add_argument("--k", type=int, default=5, help="API result limit; report includes Recall@1/3/5")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--compare-reranker", action="store_true", help="Compare hybrid retrieval with and without reranking")
    parser.add_argument("--output", help="Optional path for a JSON report")
    args = parser.parse_args()

    if not 5 <= args.k <= 20:
        parser.error("--k must be between 5 and 20 (the API limit) so Recall@5 can be measured.")

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(dataset, list) or not dataset:
        raise SystemExit("Retrieval evaluation dataset must be a non-empty JSON array.")
    required = {"id", "query", "gold_phrase", "category"}
    for index, case in enumerate(dataset):
        missing = required - set(case)
        if missing:
            raise SystemExit(f"Dataset row {index} is missing fields: {', '.join(sorted(missing))}")

    token = create_evaluation_session(args.base_url)
    report = {
        "dataset": DATASET_PATH.name,
        "dataset_size": len(dataset),
        "k": args.k,
        "cutoffs": [1, 3, 5],
        "session_note": "A dedicated evaluation session was created; it expires according to the API session TTL.",
        "modes": {},
    }

    for mode in args.modes:
        report["modes"][mode] = evaluate_mode(args.base_url, token, dataset, mode, args.k)

    if args.compare_reranker:
        if "hybrid" not in args.modes:
            report["reranker_comparison"] = {
                "available": False,
                "reason": "Include hybrid in --modes to compare reranking.",
            }
        elif not report["modes"].get("hybrid", {}).get("available"):
            report["reranker_comparison"] = {
                "available": False,
                "reason": "Hybrid retrieval is unavailable; reranker comparison was not run.",
            }
        else:
            baseline = report["modes"]["hybrid"]
            reranked = evaluate_mode(args.base_url, token, dataset, "hybrid", args.k, rerank=True)
            if not reranked.get("available"):
                report["reranker_comparison"] = reranked
            elif "applied" not in reranked.get("reranker_statuses", []):
                report["reranker_comparison"] = {
                    "available": False,
                    "reason": "Reranker was not applied. Configure RERANK_API_KEY to enable the comparison.",
                    "reranker_statuses": reranked.get("reranker_statuses", []),
                }
            else:
                report["reranker_comparison"] = {
                    "available": True,
                    "baseline_metrics": baseline["metrics"],
                    "reranked_metrics": reranked["metrics"],
                    "reranked_queries": reranked["queries"],
                }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"\nSaved report to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
