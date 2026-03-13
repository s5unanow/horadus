from __future__ import annotations

from ._docs_freshness_models import DocsFreshnessIssue, _Override


def _record_issue(
    *,
    errors: list[DocsFreshnessIssue],
    warnings: list[DocsFreshnessIssue],
    active_override_map: dict[tuple[str, str], _Override],
    rule_id: str,
    message: str,
    path: str,
) -> None:
    override = active_override_map.get((rule_id, path))
    if override is not None:
        warnings.append(
            DocsFreshnessIssue(
                level="warning",
                rule_id="docs_freshness_override_applied",
                message=(
                    f"Override active for {rule_id} in {path}: "
                    f"{override.reason} (expires {override.expires_on.isoformat()})"
                ),
                path=path,
            )
        )
        return

    errors.append(
        DocsFreshnessIssue(
            level="error",
            rule_id=rule_id,
            message=message,
            path=path,
        )
    )
