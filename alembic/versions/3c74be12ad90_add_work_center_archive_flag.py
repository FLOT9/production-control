"""Allow historical work centers to be archived."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3c74be12ad90"
down_revision: str | Sequence[str] | None = "1e2b39a7d6c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_centers",
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("work_centers", "is_archived")
