"""Sessions and accounts (Phase 2e part 1): sign-in sessions checked on every
request, lockout, password history and expiry, temporary passwords, the
security settings (platform defaults and each org's changes), and emails
stored lower-cased.

Stops, changing nothing, if two accounts' emails differ only in case: they
must be merged or one renamed by hand first.

Everyone signs in again afterwards: sign-in tokens now name their session.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMAIL_CLASHES = """
    SELECT lower(email) AS email, string_agg(email, ', ' ORDER BY email) AS accounts
    FROM users GROUP BY lower(email) HAVING count(*) > 1 ORDER BY 1
"""


def email_clash_message(rows) -> str | None:
    """The error for accounts whose emails differ only in case, or None."""
    if not rows:
        return None
    listed = "; ".join(f"{row.email}: {row.accounts}" for row in rows)
    return (
        "These accounts' emails differ only in upper/lower case, and emails are now "
        f"compared without case. Merge them or rename one, then run the upgrade again: {listed}"
    )


def upgrade() -> None:
    message = email_clash_message(op.get_bind().execute(sa.text(EMAIL_CLASHES)).all())
    if message:
        raise RuntimeError(message)
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_check_constraint("ck_users_email_lower", "users", "email = lower(email)")

    false, zero = sa.text("false"), sa.text("0")
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("users", sa.Column("is_sysadmin", sa.Boolean(), nullable=False, server_default=false))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE users SET password_changed_at = created_at")
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=false))
    op.add_column("users", sa.Column("temp_password_expires_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default=zero))
    op.add_column("users", sa.Column("failed_window_started_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True)))

    op.add_column(
        "organizations",
        sa.Column("security_settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_minutes", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.String(30)),
        sa.Column("ip", sa.String(45)),
        sa.Column("user_agent", sa.String(255)),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index(
        "ix_user_sessions_open", "user_sessions", ["user_id"], postgresql_where=sa.text("revoked_at IS NULL")
    )

    op.create_table(
        "password_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_history_user_id", "password_history", ["user_id"])

    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_table("password_history")
    op.drop_table("user_sessions")
    op.drop_column("organizations", "security_settings")
    for column in (
        "locked_until",
        "locked_at",
        "failed_window_started_at",
        "failed_login_count",
        "temp_password_expires_at",
        "must_change_password",
        "password_changed_at",
        "is_sysadmin",
        "is_active",
    ):
        op.drop_column("users", column)
    # Emails stay lower-cased: their original case isn't kept.
    op.drop_constraint("ck_users_email_lower", "users", type_="check")
