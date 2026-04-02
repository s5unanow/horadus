from __future__ import annotations


def validate_entry_title_note(title: str, note: str, *, line_number: int) -> None:
    if not title:
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: title must not be empty."
        )
    if "\n" in title or "\r" in title:
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: title must be a single line."
        )
    if not note:
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: note must not be empty."
        )


def validate_entry_promotion_fields(
    *,
    status: str,
    promoted_task_id: str | None,
    line_number: int,
) -> None:
    if status == "promoted" and promoted_task_id is None:
        raise ValueError(
            f"Invalid task intake entry at line {line_number}: promoted entries must include promoted_task_id."
        )
    if status != "promoted" and promoted_task_id is not None:
        raise ValueError(
            "Invalid task intake entry at line "
            f"{line_number}: only promoted entries may include promoted_task_id."
        )


__all__ = ["validate_entry_promotion_fields", "validate_entry_title_note"]
