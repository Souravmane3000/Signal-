from agent.state import SignalState


def hybrid_dedup(state: SignalState) -> dict:
    findings = state["scored_findings"]
    memory = state["semantic_memory"]

    # Initialise seen sets from persistent memory (lists in state, sets during run)
    seen_company_dates: set[str] = set(memory.get("seen_company_dates") or [])
    seen_urls: set[str] = set(memory.get("seen_urls") or [])
    seen_titles: set[str] = set(memory.get("seen_titles") or [])

    new_findings: list[dict] = []
    dropped = 0

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

        # Mutate in place so is_duplicate / duplicate_reason survive on the original
        # dict regardless of whether it ends up in new_findings or is dropped.
        finding["is_duplicate"] = is_duplicate
        finding["duplicate_reason"] = duplicate_reason

        if is_duplicate:
            dropped += 1
        else:
            new_findings.append(finding)
            # Update seen sets with this finding's keys
            if company and date:
                seen_company_dates.add(company + "|" + date)
            if url:
                seen_urls.add(url)
            if normalized_title:
                seen_titles.add(normalized_title)

    print(
        f"Hybrid dedup: {len(new_findings)} kept, {dropped} dropped"
    )

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
