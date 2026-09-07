"""add_users_and_task_user_id

Revision ID: 3cb47e2e50f7
Revises: b787f29a8e79
Create Date: 2026-09-08 03:20:43.085979

Changes:
  - Create users table (id, email, hashed_password, is_active, created_at)
  - Add tasks.user_id FK → users.id (NOT NULL, CASCADE DELETE)

The tasks ALTER uses batch mode so this migration works on both SQLite
(tests / CI) and PostgreSQL (production) without changes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3cb47e2e50f7"
down_revision: Union[str, Sequence[str], None] = "b787f29a8e79"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users table ──────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # ── tasks.user_id — batch mode for SQLite compat ─────────────────────
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column("user_id", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_index(
            op.f("ix_tasks_user_id"), ["user_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_tasks_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        # Remove the temporary server_default now that FK is in place
        batch_op.alter_column("user_id", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("fk_tasks_user_id_users", type_="foreignkey")
        batch_op.drop_index(op.f("ix_tasks_user_id"))
        batch_op.drop_column("user_id")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
