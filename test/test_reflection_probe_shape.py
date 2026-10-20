"""Pin reflection_probe report shape with a fake inspector (issue #857)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import sqlalchemy.types

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SPEC = importlib.util.spec_from_file_location(
    "reflection_probe",
    REPO_ROOT / "scripts/reflection_probe.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
probe_table = MODULE.probe_table
_serialize = MODULE._serialize


class _CountingInspector:
    METHODS = (
        "get_columns",
        "get_pk_constraint",
        "get_foreign_keys",
        "get_indexes",
        "get_unique_constraints",
        "get_table_comment",
    )

    def __init__(self) -> None:
        self.calls: dict[str, int] = {name: 0 for name in self.METHODS}

    def get_columns(self, table_name: str):  # noqa: ANN001, ANN202
        self.calls["get_columns"] += 1
        return ["columns-sentinel"]

    def get_pk_constraint(self, table_name: str):  # noqa: ANN001, ANN202
        self.calls["get_pk_constraint"] += 1
        return {"constrained_columns": ["pk-sentinel"]}

    def get_foreign_keys(self, table_name: str):  # noqa: ANN001, ANN202
        self.calls["get_foreign_keys"] += 1
        return ["foreign-keys-sentinel"]

    def get_indexes(self, table_name: str):  # noqa: ANN001, ANN202
        self.calls["get_indexes"] += 1
        return ["indexes-sentinel"]

    def get_unique_constraints(self, table_name: str):  # noqa: ANN001, ANN202
        self.calls["get_unique_constraints"] += 1
        return ["unique-constraints-sentinel"]

    def get_table_comment(self, table_name: str):  # noqa: ANN001, ANN202
        self.calls["get_table_comment"] += 1
        return {"text": "table-comment-sentinel"}


def test_probe_table_returns_exact_report_keys() -> None:
    report = probe_table(_CountingInspector(), "users")
    assert set(report) == {
        "columns",
        "pk_constraint",
        "foreign_keys",
        "indexes",
        "unique_constraints",
        "table_comment",
    }


def test_probe_table_calls_each_method_once() -> None:
    inspector = _CountingInspector()
    probe_table(inspector, "users")
    assert inspector.calls == {name: 1 for name in _CountingInspector.METHODS}


def test_probe_table_pins_each_value_to_its_inspector_method() -> None:
    report = probe_table(_CountingInspector(), "users")
    assert report == {
        "columns": ["columns-sentinel"],
        "pk_constraint": {"constrained_columns": ["pk-sentinel"]},
        "foreign_keys": ["foreign-keys-sentinel"],
        "indexes": ["indexes-sentinel"],
        "unique_constraints": ["unique-constraints-sentinel"],
        "table_comment": {"text": "table-comment-sentinel"},
    }


def test_serialize_type_class_is_module_qualified() -> None:
    assert _serialize(sqlalchemy.types.Integer) == "sqlalchemy.sql.sqltypes.Integer"


def test_report_with_type_class_serializes_to_stable_json() -> None:
    report = {"columns": [{"name": "n", "type": sqlalchemy.types.Integer}]}
    serialized = json.dumps(report, default=_serialize, sort_keys=True)
    expected = '{"columns": [{"name": "n", "type": "sqlalchemy.sql.sqltypes.Integer"}]}'
    assert serialized == expected


def test_serialize_plain_values_are_strings() -> None:
    assert _serialize(42) == "42"
    assert _serialize(None) == "None"
