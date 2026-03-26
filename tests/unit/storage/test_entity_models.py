from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.storage.entity_models import CanonicalEntity, CanonicalEntityAlias, EventEntity

pytestmark = pytest.mark.unit


def test_canonical_entity_constraints_and_indexes_present() -> None:
    constraint_names = {
        constraint.name
        for constraint in CanonicalEntity.__table__.constraints
        if getattr(constraint, "name", None)
    }
    index_names = {index.name for index in CanonicalEntity.__table__.indexes}

    assert "check_canonical_entities_type_allowed" in constraint_names
    assert "uq_canonical_entities_type_normalized_name" in constraint_names
    assert "idx_canonical_entities_type_name" in index_names


def test_canonical_entity_alias_constraints_and_indexes_present() -> None:
    constraint_names = {
        constraint.name
        for constraint in CanonicalEntityAlias.__table__.constraints
        if getattr(constraint, "name", None)
    }
    index_names = {index.name for index in CanonicalEntityAlias.__table__.indexes}

    assert "uq_canonical_entity_aliases_entity_alias" in constraint_names
    assert "idx_canonical_entity_aliases_normalized_alias" in index_names


def test_event_entity_constraints_and_indexes_present() -> None:
    constraint_names = {
        constraint.name
        for constraint in EventEntity.__table__.constraints
        if getattr(constraint, "name", None)
    }
    index_names = {index.name for index in EventEntity.__table__.indexes}

    assert "check_event_entities_role_allowed" in constraint_names
    assert "check_event_entities_type_allowed" in constraint_names
    assert "check_event_entities_resolution_status_allowed" in constraint_names
    assert "uq_event_entities_event_mention" in constraint_names
    assert "idx_event_entities_event_role" in index_names
    assert "idx_event_entities_canonical_entity" in index_names


def test_entity_models_module_imports_without_circular_dependency() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; importlib.import_module('src.storage.entity_models')",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
