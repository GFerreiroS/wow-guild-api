"""Add User and user_id FK to GuildMember

Revision ID: f0e0168717ac
Revises: 6cda05b826ee
Create Date: 2025-07-03 21:32:08.205903

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0e0168717ac"
down_revision: Union[str, Sequence[str], None] = "6cda05b826ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1) Drop any existing user table along with its dependents
    op.execute('DROP TABLE IF EXISTS "user" CASCADE')

    # 2) (Re)create the user table
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # 3) Add the user_id column to guildmember
    op.add_column("guildmember", sa.Column("user_id", sa.Integer(), nullable=True))

    # 4) Create foreign key constraint from guildmember.user_id → user.id
    op.create_foreign_key(
        "fk_guildmember_user",
        source_table="guildmember",
        referent_table="user",
        local_cols=["user_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint("fk_guildmember_user", "guildmember", type_="foreignkey")
    op.drop_column("guildmember", "user_id")
    op.execute('DROP TABLE IF EXISTS "user" CASCADE')

    op.create_table(
        "user",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("username", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("password", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("role", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("user_pkey")),
    )
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)
    # ### end Alembic commands ###
