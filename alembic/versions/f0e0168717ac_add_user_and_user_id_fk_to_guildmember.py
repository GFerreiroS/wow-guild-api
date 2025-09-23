"""Add user table and link guild members to users.

Revision ID: f0e0168717ac
Revises: 6cda05b826ee
Create Date: 2025-07-03 21:32:08.205903

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0e0168717ac"
down_revision: Union[str, Sequence[str], None] = "6cda05b826ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USER_TABLE_NAME = "user"
USER_INDEX_NAME = "ix_user_username"
FK_NAME = "fk_guildmember_user"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if USER_TABLE_NAME not in inspector.get_table_names():
        op.create_table(
            USER_TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("password", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(USER_INDEX_NAME, USER_TABLE_NAME, ["username"], unique=True)
    else:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(USER_TABLE_NAME)}
        if USER_INDEX_NAME not in existing_indexes:
            op.create_index(USER_INDEX_NAME, USER_TABLE_NAME, ["username"], unique=True)

    guildmember_columns = {
        column["name"] for column in inspector.get_columns("guildmember")
    }
    if "user_id" not in guildmember_columns:
        op.add_column("guildmember", sa.Column("user_id", sa.Integer(), nullable=True))

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("guildmember")}
    if FK_NAME not in fk_names:
        op.create_foreign_key(
            FK_NAME,
            source_table="guildmember",
            referent_table=USER_TABLE_NAME,
            local_cols=["user_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("guildmember")}
    if FK_NAME in fk_names:
        op.drop_constraint(FK_NAME, "guildmember", type_="foreignkey")

    guildmember_columns = {
        column["name"] for column in inspector.get_columns("guildmember")
    }
    if "user_id" in guildmember_columns:
        op.drop_column("guildmember", "user_id")

    if USER_TABLE_NAME in inspector.get_table_names():
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(USER_TABLE_NAME)}
        if USER_INDEX_NAME in existing_indexes:
            op.drop_index(USER_INDEX_NAME, table_name=USER_TABLE_NAME)
        op.drop_table(USER_TABLE_NAME)
