"""Protect physical schema declarations independently of migration reflection."""

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from app.db.base import Base
from app.db.types import str_enum
from app.models.enums import ScanStatus


@pytest.mark.parametrize("table,column", [
    ("findings", "domain"), ("findings", "severity"),
    ("org_memberships", "role"), ("reports", "status"),
    ("risk_scores", "dimension"), ("risk_scores", "tier"), ("scans", "status"),
])
def test_legacy_enum_columns_preserve_varchar_50(table, column):
    field = Base.metadata.tables[table].c[column]
    assert field.type.compile(dialect=postgresql.dialect()) == "VARCHAR(50)"


def test_enum_lengths_are_explicit_only_when_requested():
    assert str_enum(ScanStatus).length == max(len(item.value) for item in ScanStatus)
    assert str_enum(ScanStatus, length=50).length == 50
    assert str_enum(ScanStatus, length=50).validate_strings
    assert not str_enum(ScanStatus, length=50).native_enum


def test_email_uniqueness_and_lookup_index_are_both_preserved():
    table = Base.metadata.tables["users"]
    constraints = [item for item in table.constraints if isinstance(item, UniqueConstraint)]
    assert any(item.name == "users_email_key" and list(item.columns.keys()) == ["email"] for item in constraints)
    lookup = next(item for item in table.indexes if item.name == "ix_users_email")
    assert list(lookup.columns.keys()) == ["email"]
    assert not lookup.unique


@pytest.mark.parametrize("table,index,columns", [
    ("reports", "ix_reports_org_created", ["org_id", "created_at"]),
    ("reports", "ix_reports_org_status", ["org_id", "status"]),
    ("documents", "ix_documents_org_framework", ["org_id", "framework"]),
])
def test_composite_indexes_keep_their_leading_organization_column(table, index, columns):
    declared = next(item for item in Base.metadata.tables[table].indexes if item.name == index)
    assert list(declared.columns.keys()) == columns
