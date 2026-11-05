"""Fixed ranks shared by seek queries and their physical sort index."""
from sqlalchemy import case, func, literal_column, text
from sqlalchemy.sql.expression import Grouping
from app.models.enums import Severity


def severity_rank(column):
    return Grouping(case(*((column == literal_column("'" + value.value + "'"), literal_column(str(rank)))
                  for rank, value in enumerate(Severity))))


def severity_rank_index():
    # PostgreSQL reflects implicit varchar casts and an explicit NULL ELSE.
    # Keep the DDL spelling stable for Alembic comparison, without binding
    # values in the query expression that must match this physical index.
    return text("(\nCASE\n" + "\n".join(
        f"    WHEN severity::text = '{value.value}'::text THEN {rank}"
        for rank, value in enumerate(Severity)) + "\n    ELSE NULL::integer\nEND)")


def finding_text(model):
    return func.lower(func.coalesce(model.description, model.category))


def finding_text_size(model):
    return func.coalesce(func.octet_length(finding_text(model)), literal_column("0"))


TEXT_SORT_BYTES = 1024
SHORT_FINDING_TEXT = text("archived_at IS NULL AND COALESCE(octet_length(lower(COALESCE(description, category::text))), 0) <= 1024")
LONG_FINDING_TEXT = text("archived_at IS NULL AND COALESCE(octet_length(lower(COALESCE(description, category::text))), 0) > 1024")
