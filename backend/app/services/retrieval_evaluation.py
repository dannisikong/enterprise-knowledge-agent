from __future__ import annotations

DEFAULT_CUTOFFS = (1, 3, 5)


def _contains_evidence(result: dict, evidence_phrases: list[str]) -> bool:
    content = result.get("content", "")
    return any(phrase in content for phrase in evidence_phrases)


def reciprocal_rank(results: list[dict], gold_phrase: str) -> float:
    """Return reciprocal rank of the first result containing the gold phrase."""
    for rank, result in enumerate(results, start=1):
        if gold_phrase in result.get("content", ""):
            return 1.0 / rank
    return 0.0


def recall_at_k(results: list[dict], gold_phrase: str, k: int = 5) -> float:
    """Single-gold-passage recall: 1 when the relevant passage appears in top k."""
    if k < 1:
        raise ValueError("k must be greater than or equal to 1.")
    return float(any(gold_phrase in item.get("content", "") for item in results[:k]))


def _evidence_phrases(required_evidence: list[dict | str]) -> list[str]:
    phrases = [
        item if isinstance(item, str) else item.get("evidence_phrase", "")
        for item in required_evidence
    ]
    return [phrase for phrase in phrases if phrase]


def evaluate_query(
    results: list[dict],
    gold_phrase: str | None = None,
    k: int = 5,
    cutoffs: tuple[int, ...] = DEFAULT_CUTOFFS,
    *,
    required_evidence: list[dict | str] | None = None,
    expected_source_documents: list[str] | None = None,
    answerable: bool = True,
) -> dict:
    """Evaluate a legacy single-gold query or a B2 multi-evidence query.

    For unanswerable questions, report whether retrieval returned candidates.
    This is deliberately named as a non-empty-candidate signal, not a false
    positive rate: relevance and answer abstention require separate judgments.
    """
    if k < 1:
        raise ValueError("k must be greater than or equal to 1.")

    if not answerable:
        metrics = {
            f"no_answer_nonempty@{cutoff}": float(bool(results[:cutoff]))
            for cutoff in cutoffs
        }
        if k not in cutoffs:
            metrics[f"no_answer_nonempty@{k}"] = float(bool(results[:k]))
        return metrics

    phrases = _evidence_phrases(required_evidence or [])
    if not phrases and gold_phrase:
        phrases = [gold_phrase]
    if not phrases:
        raise ValueError("An answerable query requires gold_phrase or required_evidence.")

    metrics = {
        f"recall@{cutoff}": float(
            any(_contains_evidence(item, phrases) for item in results[:cutoff])
        )
        for cutoff in cutoffs
    }
    if k not in cutoffs:
        metrics[f"recall@{k}"] = float(
            any(_contains_evidence(item, phrases) for item in results[:k])
        )

    first_relevant_rank = next(
        (
            rank
            for rank, item in enumerate(results, start=1)
            if _contains_evidence(item, phrases)
        ),
        None,
    )
    metrics["mrr"] = 1.0 / first_relevant_rank if first_relevant_rank else 0.0

    if required_evidence is not None:
        metrics.update({
            f"evidence_recall@{cutoff}": round(
                sum(
                    any(phrase in item.get("content", "") for item in results[:cutoff])
                    for phrase in phrases
                ) / len(phrases),
                4,
            )
            for cutoff in cutoffs
        })
        if k not in cutoffs:
            metrics[f"evidence_recall@{k}"] = round(
                sum(
                    any(phrase in item.get("content", "") for item in results[:k])
                    for phrase in phrases
                ) / len(phrases),
                4,
            )
        for cutoff in (*cutoffs, *((k,) if k not in cutoffs else ())):
            found_count = sum(
                any(phrase in item.get("content", "") for item in results[:cutoff])
                for phrase in phrases
            )
            metrics[f"evidence_complete@{cutoff}"] = float(found_count == len(phrases))

    if expected_source_documents is not None:
        expected = set(expected_source_documents)
        if expected:
            for cutoff in (*cutoffs, *((k,) if k not in cutoffs else ())):
                found_sources = {
                    item.get("filename")
                    for item in results[:cutoff]
                    if item.get("filename") in expected
                }
                metrics[f"source_coverage@{cutoff}"] = round(
                    len(found_sources) / len(expected), 4
                )
        else:
            for cutoff in (*cutoffs, *((k,) if k not in cutoffs else ())):
                metrics[f"source_coverage@{cutoff}"] = 0.0

    return metrics


def aggregate_metrics(rows: list[dict], k: int = 5) -> dict:
    if not rows:
        return {
            "recall@1": 0.0,
            "recall@3": 0.0,
            "recall@5": 0.0,
            **({f"recall@{k}": 0.0} if k not in DEFAULT_CUTOFFS else {}),
            "mrr": 0.0,
            "query_count": 0,
        }

    keys = sorted({
        key
        for row in rows
        for key in row
        if key.startswith(("recall@", "evidence_recall@", "evidence_complete@", "source_coverage@", "no_answer_nonempty@"))
        or key == "mrr"
    })
    return {
        **{
            key: round(
                sum(row[key] for row in rows if key in row)
                / sum(key in row for row in rows),
                4,
            )
            for key in keys
        },
        "query_count": len(rows),
    }
