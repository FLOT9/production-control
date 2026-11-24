"""Add the work center recorded at product aggregation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1e2b39a7d6c4"
down_revision: str | Sequence[str] | None = "174cc4eefdca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("aggregation_work_center_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "aggregation_work_center_id")
