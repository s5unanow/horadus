from __future__ import annotations


def document_paths(documents: list[dict[str, object]]) -> set[str]:
    return {str(document["path"]) for document in documents}


def included_orientation_paths(data: dict[str, object]) -> set[str]:
    included = data["retrieval_sources"]["included"]
    return {
        str(source["path"])
        for source in included
        if source.get("reason") == "compact orientation metadata"
    }


def registry_paths(data: dict[str, object]) -> set[str]:
    entries = data["policy"]["legacy_policy_registry"]["entries"]
    return {str(entry["path"]) for entry in entries}


def excluded_sources(data: dict[str, object]) -> set[str]:
    excluded = data["retrieval_sources"]["excluded"]
    return {str(source["source"]) for source in excluded}
