"""Hybrid Dedup — Stages 0–2 deterministic + Stage 3 embedding similarity."""

from __future__ import annotations

import math
import os
import re
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from openai import OpenAI

from agent.state import SignalState

# Locked by DEC-014 — do not change or make configurable.
_EMBEDDING_MODEL = "text-embedding-3-small"
_HARD_DUP_THRESHOLD = 0.85
_NEAR_DUP_FLOOR = 0.75
_SUMMARY_SNIPPET_CHARS = 300
_DEDUP_EMBEDDING_NS_SUFFIX = "dedup_embeddings"


def _encode_db_url(url: str) -> str:
    match = re.match(
        r"^(postgresql(?:\+\w+)?://)([^:@/]+):(.+)@([^/]+)(/.*)?$",
        url,
    )
    if not match:
        return url
    scheme, user, password, hostport, path = match.groups()
    return f"{scheme}{user}:{quote(password, safe='')}@{hostport}{path or ''}"


def _get_postgres_store():
    """Reuse the PostgresStore from SIG-P2-002 — do not open a second store."""
    from agent.graph import _postgres_store

    if _postgres_store is None:
        raise RuntimeError("PostgresStore unavailable (SIG-P2-002 not complete).")
    return _postgres_store


def _embedding_text(finding: dict) -> str:
    """Spike 3 input shape: title + first 300 characters of summary."""
    title = finding.get("title") or ""
    summary = (finding.get("summary") or "")[:_SUMMARY_SNIPPET_CHARS]
    return f"{title} {summary}".strip()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed texts with text-embedding-3-small. One API call per batch."""
    if not texts:
        return []
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.embeddings.create(model=_EMBEDDING_MODEL, input=texts)
    by_index = {item.index: item.embedding for item in response.data}
    return [by_index[i] for i in range(len(texts))]


def _parse_pgvector(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if not text:
        return None
    return [float(x) for x in text.split(",")]


def _load_briefing_item_embeddings() -> list[list[float]]:
    """Read-only: load prior embeddings already persisted on briefing_items."""
    load_dotenv()
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        return []
    try:
        import psycopg

        url = _encode_db_url(raw_url)
        with psycopg.connect(url) as conn:
            rows = conn.execute(
                "SELECT embedding::text FROM briefing_items "
                "WHERE embedding IS NOT NULL"
            ).fetchall()
        out: list[list[float]] = []
        for (raw,) in rows:
            parsed = _parse_pgvector(raw)
            if parsed:
                out.append(parsed)
        return out
    except Exception:
        return []


def _load_store_embeddings(store, user_id: str) -> list[list[float]]:
    namespace = ("user", user_id, _DEDUP_EMBEDDING_NS_SUFFIX)
    items = store.search(namespace, limit=1000)
    out: list[list[float]] = []
    for item in items:
        value = item.value if isinstance(item.value, dict) else {}
        emb = value.get("embedding")
        if isinstance(emb, list) and emb:
            out.append([float(x) for x in emb])
    return out


def _persist_embedding_to_store(
    store,
    user_id: str,
    finding: dict,
    embedding: list[float],
) -> None:
    """Cache embedding in PostgresStore for future semantic lookup.

    Does NOT write briefing_items — that row is created later; the embedding
    is attached to the finding for the eventual insert path.
    """
    source_url = finding.get("source_url") or ""
    key = source_url or _embedding_text(finding)[:120]
    namespace = ("user", user_id, _DEDUP_EMBEDDING_NS_SUFFIX)
    store.put(
        namespace,
        key,
        {
            "embedding": embedding,
            "title": finding.get("title", ""),
            "source_url": source_url,
            "model": _EMBEDDING_MODEL,
        },
    )


def _max_similarity(embedding: list[float], corpus: list[list[float]]) -> float:
    if not corpus:
        return 0.0
    return max(_cosine_similarity(embedding, prior) for prior in corpus)


def hybrid_dedup(state: SignalState) -> dict:
    findings = state["scored_findings"]
    memory = state["semantic_memory"]
    user_id = state.get("user_id") or "user_001"

    # Initialise seen sets from persistent memory (lists in state, sets during run)
    seen_company_dates: set[str] = set(memory.get("seen_company_dates") or [])
    seen_urls: set[str] = set(memory.get("seen_urls") or [])
    seen_titles: set[str] = set(memory.get("seen_titles") or [])

    new_findings: list[dict] = []
    dropped = 0
    stage3_candidates: list[dict] = []

    for finding in findings:
        entities = finding.get("entities") or {}
        company = entities.get("company_name_normalized") or ""
        date = entities.get("announced_date") or ""
        url = finding.get("source_url", "")
        normalized_title = finding.get("title", "").lower().strip()

        is_duplicate = False
        duplicate_reason = None

        # Stage 0 — company + date pre-filter (only when both fields are present)
        if company and date:
            key = company + "|" + date
            if key in seen_company_dates:
                is_duplicate = True
                duplicate_reason = "pre_filter"

        # Stage 1 — exact URL match
        if not is_duplicate:
            if url and url in seen_urls:
                is_duplicate = True
                duplicate_reason = "url_match"

        # Stage 2 — normalised title match
        if not is_duplicate:
            if normalized_title and normalized_title in seen_titles:
                is_duplicate = True
                duplicate_reason = "title_match"

        # Mutate in place so is_duplicate / duplicate_reason survive on dropped findings.
        finding["is_duplicate"] = is_duplicate
        finding["duplicate_reason"] = duplicate_reason

        if is_duplicate:
            dropped += 1
        else:
            # Tentatively record in seen sets so later findings in this batch
            # still hit Stages 0–2. Rolled back if Stage 3 drops the finding.
            if company and date:
                seen_company_dates.add(company + "|" + date)
            if url:
                seen_urls.add(url)
            if normalized_title:
                seen_titles.add(normalized_title)
            stage3_candidates.append(finding)

    # Stage 3 — embedding cosine similarity (text-embedding-3-small, threshold 0.85)
    store = _get_postgres_store()
    prior_embeddings = _load_store_embeddings(store, user_id)
    prior_embeddings.extend(_load_briefing_item_embeddings())

    texts = [_embedding_text(f) for f in stage3_candidates]
    embeddings = _embed_texts(texts) if texts else []

    kept_run_embeddings: list[list[float]] = []

    for finding, embedding in zip(stage3_candidates, embeddings):
        entities = finding.get("entities") or {}
        company = entities.get("company_name_normalized") or ""
        date = entities.get("announced_date") or ""
        url = finding.get("source_url", "")
        normalized_title = finding.get("title", "").lower().strip()

        corpus = prior_embeddings + kept_run_embeddings
        similarity = _max_similarity(embedding, corpus)

        if similarity > _HARD_DUP_THRESHOLD:
            finding["is_duplicate"] = True
            finding["duplicate_reason"] = "embedding_similarity"
            dropped += 1
            # Roll back tentative Stage 0–2 seen-set entries for this finding.
            if company and date:
                seen_company_dates.discard(company + "|" + date)
            if url:
                seen_urls.discard(url)
            if normalized_title:
                seen_titles.discard(normalized_title)
            continue

        finding["is_duplicate"] = False
        finding["duplicate_reason"] = None
        # Preserve embedding on the finding for later briefing_items INSERT.
        finding["embedding"] = embedding
        if similarity >= _NEAR_DUP_FLOOR:
            finding["related_to_previous_coverage"] = True

        new_findings.append(finding)
        kept_run_embeddings.append(embedding)
        _persist_embedding_to_store(store, user_id, finding, embedding)

    print(f"Hybrid dedup: {len(new_findings)} kept, {dropped} dropped")

    updated_memory = {
        **memory,
        "seen_company_dates": list(seen_company_dates),
        "seen_urls": list(seen_urls),
        "seen_titles": list(seen_titles),
    }

    return {
        "new_findings": new_findings,
        "findings_dropped_dedup": dropped,
        "semantic_memory": updated_memory,
    }
