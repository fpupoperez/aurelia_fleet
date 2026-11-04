"""Score the checked-in questions against the current index."""

import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.db.session import session_scope
from app.providers import build_embedding_provider
from app.retrieval.search import search


def load_questions(path: Path) -> list[dict]:
    """Read the checked-in questions that define the retrieval calibration set."""
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(settings: Settings | None = None) -> dict[str, float]:
    """Score recall and abstention. The set expects the fake embedder's distances."""
    resolved = settings or get_settings()
    questions = load_questions(Path(resolved.evaluation_path))
    embedder = build_embedding_provider(resolved)
    recall_hits = 0
    recall_total = 0
    abstain_hits = 0
    abstain_total = 0
    with session_scope() as session:
        for item in questions:
            result = search(
                session,
                settings=resolved,
                embedder=embedder,
                tenant_id=resolved.default_tenant,
                question=item["question"],
                equipment_model=item.get("equipmentModel"),
                k=item.get("k", resolved.retrieval_k_default),
            )
            if item.get("expectAbstain"):
                abstain_total += 1
                if result.abstained:
                    abstain_hits += 1
                continue
            recall_total += 1
            snippet = item["expectSnippet"]
            if any(snippet in hit.content for hit in result.hits):
                recall_hits += 1
    recall = 1.0 if recall_total == 0 else recall_hits / recall_total
    abstention = 1.0 if abstain_total == 0 else abstain_hits / abstain_total
    return {
        "recall_at_k": recall,
        "abstention_accuracy": abstention,
        "recall_total": float(recall_total),
        "abstain_total": float(abstain_total),
    }


def main() -> None:
    """Print the scores. make eval runs this."""
    scores = evaluate()
    print(
        f"recall@k={scores['recall_at_k']:.2f} "
        f"abstention_accuracy={scores['abstention_accuracy']:.2f}"
    )
