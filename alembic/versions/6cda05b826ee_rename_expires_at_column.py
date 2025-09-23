"""Ensure OAuth token expiry column is named consistently.

Revision ID: 6cda05b826ee
Revises: 19c2e5cbbc1e
Create Date: 2025-06-28 19:04:20.274593

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6cda05b826ee"
down_revision: Union[str, Sequence[str], None] = "19c2e5cbbc1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("oauthtoken")}

    if "expiret_at" in columns and "expires_at" not in columns:
        with op.batch_alter_table("oauthtoken") as batch_op:
            batch_op.alter_column("expiret_at", new_column_name="expires_at")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("oauthtoken")}

    if "expires_at" in columns and "expiret_at" not in columns:
        with op.batch_alter_table("oauthtoken") as batch_op:
            batch_op.alter_column("expires_at", new_column_name="expiret_at")
