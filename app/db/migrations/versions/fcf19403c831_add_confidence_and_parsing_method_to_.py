"""add_confidence_and_parsing_method_to_emails

Revision ID: fcf19403c831
Revises: c0a0c074cf92
Create Date: 2025-11-07 20:48:37.487039

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcf19403c831'
down_revision: Union[str, None] = 'c0a0c074cf92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add confidence column (alias for parsing_confidence)
    op.add_column(
        'emails',
        sa.Column(
            'confidence',
            sa.Numeric(precision=5, scale=4),
            nullable=True,
            comment='Alias for parsing_confidence (for compatibility)'
        )
    )
    
    # Add parsing_method column
    op.add_column(
        'emails',
        sa.Column(
            'parsing_method',
            sa.String(length=50),
            nullable=True,
            comment='Parsing method used (llm, regex, hybrid)'
        )
    )


def downgrade() -> None:
    # Remove the added columns
    op.drop_column('emails', 'parsing_method')
    op.drop_column('emails', 'confidence')
