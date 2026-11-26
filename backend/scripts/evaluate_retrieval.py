from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.retrieval_evaluation import aggregate_metrics, evaluate_query  # noqa: E402

B2_DIR = BACKEND_DIR / "evaluation" / "b2"
DEFAULT_DATASET_PATH = B2_DIR / "retrieval_dataset_b2.json"
DEFAULT_DOCUMENTS_DIR = B2_DIR / "documents"
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
    except (URLError, TimeoutError) as error:
        raise SystemExit(f"Unable to create evaluation session: {error}") from error
    token = session.get("token")
    if not isinstance(token, str) or not token:
        raise SystemExit("Session endpoint did not return a usable token.")
    return token


def upload_evaluation_document(base_url: str, token: str, document_path: Path) -> dict:
    if not document_path.is_file():
        raise SystemExit(f"Evaluation document not found: {document_path}")

    boundary = "----EnterpriseKnowledgeAgentB2EvaluationBoundary"
    file_bytes = document_path.read_bytes()
    content_type = mimetypes.guess_type(document_path.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{document_path.name}"\r\n'
        f"Content-Type: {content_type}; charset=utf-8\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/documents",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Session-Token": token,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"Unable to upload {document_path.name} (HTTP {error.code}): {message}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise SystemExit(f"Unable to upload {document_path.name}: {error}") from error


def load_b2_dataset(dataset_path: Path, documents_dir: Path) -> tuple[dict, list[dict], list[Path]]:
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Unable to read B2 dataset {dataset_path}: {error}") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise SystemExit("B2 dataset must be an object containing a questions array.")
    questions = payload["questions"]
    if not questions:
        raise SystemExit("B2 dataset questions array must not be empty.")

    document_names = payload.get("documents")
    if not isinstance(document_names, list) or not document_names:
        raise SystemExit("B2 dataset must declare a non-empty documents array.")
    document_paths = []
    for name in document_names:
        if not isinstance(name, str) or Path(name).name != name:
            raise SystemExit(f"Invalid document filename in dataset: {name!r}")
        path = documents_dir / name
        if not path.is_file():
            raise SystemExit(f"Dataset document is missing: {path}")
        document_paths.append(path)

    seen_ids = set()
    for index, case in enumerate(questions):
        if not isinstance(case, dict):
            raise SystemExit(f"Question at index {index} must be an object.")
        required = {"id", "category", "query", "answerable", "required_evidence", "expected_source_documents"}
        missing = required - set(case)
        if missing:
            raise SystemExit(f"Question at index {index} is missing fields: {', '.join(sorted(missing))}")
        if case["id"] in seen_ids:
            raise SystemExit(f"Duplicate question id: {case['id']}")
        seen_ids.add(case["id"])
        if not isinstance(case["query"], str) or not case["query"].strip():
            raise SystemExit(f"Question {case['id']} has an empty query.")
        if not isinstance(case["answerable"], bool):
            raise SystemExit(f"Question {case['id']} answerable must be boolean.")
        evidence = case["required_evidence"]
        sources = case["expected_source_documents"]
        if not isinstance(evidence, list) or not isinstance(sources, list):
            raise SystemExit(f"Question {case['id']} evidence and source fields must be arrays.")
        if case["answerable"] and not evidence:
            raise SystemExit(f"Answerable question {case['id']} has no required evidence.")
        if not case["answerable"] and (evidence or sources):
            raise SystemExit(f"No-answer question {case['id']} must have empty evidence and source arrays.")
        for item in evidence:
            if not isinstance(item, dict) or not item.get("document") or not item.get("evidence_phrase"):
                raise SystemExit(f"Question {case['id']} contains an invalid evidence item.")
            if item["document"] not in document_names:
                raise SystemExit(f"Question {case['id']} references unknown document {item['document']!r}.")

    return payload, questions, document_paths


def post_search(
    base_url: str,
    token: str,
    query: str,
    mode: str,
    limit: int,
    rerank: bool = False,
) -> dict:
    return post_json(
        f"{base_url.rstrip('/')}/search",
        {"query": query, "mode": mode, "limit": limit, "rerank": rerank},
        token,
    )


def _gold_rank(results: list[dict], evidence: list[dict]) -> int | None:
    phrases = [item["evidence_phrase"] for item in evidence]
    return next(
        (
            rank
            for rank, item in enumerate(results, start=1)
            if any(phrase in item.get("content", "") for phrase in phrases)
        ),
        None,
    )


def evaluate_mode(
    base_url: str,
    token: str,
    dataset: list[dict],
    mode: str,
    limit: int,
    rerank: bool = False,
) -> dict:
    query_rows = []
    details = []
    effective_modes = set()
    reranker_statuses = set()

    for case in dataset:
        try:
            response = post_search(base_url, token, case["query"], mode, limit, rerank)
        except HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            if mode in ("vector", "hybrid"):
                return {"available": False, "reason": f"{mode.title()} mode unavailable (HTTP {error.code}): {message}"}
            raise SystemExit(
                f"Search failed for {case['id']} in {mode} mode (HTTP {error.code}): {message}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise SystemExit(f"Cannot reach API at {base_url}: {error}") from error

        effective_mode = response.get("mode")
        if effective_mode != mode:
            return {
                "available": False,
                "reason": f"{mode} requested but API returned {effective_mode!r}.",
            }

        results = response.get("results", [])
        if not isinstance(results, list):
            raise SystemExit(f"Search response for {case['id']} did not contain a results array.")

        metrics = evaluate_query(
            results,
            k=limit,
            required_evidence=case["required_evidence"],
            expected_source_documents=case["expected_source_documents"],
            answerable=case["answerable"],
        )
        query_rows.append(metrics)
        effective_modes.add(effective_mode)
        reranker_statuses.add(response.get("reranker", "unknown"))

        detail = {
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "answerable": case["answerable"],
            "effective_mode": effective_mode,
            **metrics,
            "first_result": results[0].get("filename") if results else None,
            "gold_rank": _gold_rank(results, case["required_evidence"]) if case["answerable"] else None,
            "retrieved_sources": list(dict.fromkeys(
                item.get("filename") for item in results if item.get("filename")
            )),
        }
        details.append(detail)

    category_rows: dict[str, list[dict]] = defaultdict(list)
    for case, metrics in zip(dataset, query_rows):
        category_rows[case["category"]].append(metrics)

    return {
        "available": True,
        "metrics": aggregate_metrics(query_rows, limit),
        "category_breakdown": {
            category: aggregate_metrics(rows, limit)
            for category, rows in sorted(category_rows.items())
        },
        "effective_modes": sorted(effective_modes),
        "reranker_statuses": sorted(reranker_statuses),
        "queries": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Keyword, Vector and Hybrid retrieval against the multi-document B2 corpus."
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI base URL")
    parser.add_argument("--k", type=int, default=5, help="API result limit; report includes Recall@1/3/5")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH, help="B2 dataset JSON path")
    parser.add_argument("--documents-dir", type=Path, default=DEFAULT_DOCUMENTS_DIR, help="Directory containing B2 corpus files")
    parser.add_argument("--compare-reranker", action="store_true", help="Compare Hybrid retrieval with and without reranking")
    parser.add_argument("--output", type=Path, help="Optional path for a JSON report")
    args = parser.parse_args()

    if not 5 <= args.k <= 20:
        parser.error("--k must be between 5 and 20 (the API limit) so Recall@5 can be measured.")

    dataset_meta, dataset, document_paths = load_b2_dataset(args.dataset, args.documents_dir)
    token = create_evaluation_session(args.base_url)

    uploaded_documents = []
    for document_path in document_paths:
        uploaded = upload_evaluation_document(args.base_url, token, document_path)
        uploaded_documents.append({
            "filename": uploaded.get("filename", document_path.name),
            "chunk_count": uploaded.get("chunk_count"),
            "embedding_status": uploaded.get("embedding_status"),
        })

    report = {
        "dataset": str(args.dataset),
        "dataset_name": dataset_meta.get("dataset_name"),
        "dataset_version": dataset_meta.get("version"),
        "dataset_size": len(dataset),
        "document_count": len(uploaded_documents),
        "category_counts": dataset_meta.get("categories", {}),
        "k": args.k,
        "cutoffs": [1, 3, 5],
        "session_note": "All corpus documents and retrieval queries use one dedicated evaluation session.",
        "embedding_model_assumption": "The existing embedding model/configuration is unchanged.",
        "uploaded_documents": uploaded_documents,
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
                    "reranked_category_breakdown": reranked["category_breakdown"],
                    "reranked_queries": reranked["queries"],
                }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"\nSaved report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
