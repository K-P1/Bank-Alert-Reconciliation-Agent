"""drop_action_audits_table

Revision ID: fe83cc6ad3ec
Revises: 9d854018b949
Create Date: 2025-11-16 17:04:51.101698

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fe83cc6ad3ec"
down_revision: Union[str, None] = "9d854018b949"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop action_audits table - no longer needed after workflow/action system removal."""
    op.drop_table("action_audits")


def downgrade() -> None:
    """Recreate action_audits table if downgrading."""
    op.create_table(
        "action_audits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_audits_action_id", "action_audits", ["action_id"])
    op.create_index("ix_action_audits_status", "action_audits", ["status"])
    op.create_index("ix_action_audits_started_at", "action_audits", ["started_at"])
