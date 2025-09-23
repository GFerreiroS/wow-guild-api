"""Initial schema for guild members and OAuth tokens.

Revision ID: 19c2e5cbbc1e
Revises:
Create Date: 2025-06-28 19:00:18.240896

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19c2e5cbbc1e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guildmember",
        sa.Column("character_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("realm", sa.String(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("race", sa.String(), nullable=False),
        sa.Column("clazz", sa.String(), nullable=False),
        sa.Column("faction", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "oauthtoken",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("oauthtoken")
    op.drop_table("guildmember")
