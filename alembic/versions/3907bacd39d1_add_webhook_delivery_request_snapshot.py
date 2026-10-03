"""add webhook delivery request snapshot

Revision ID: 3907bacd39d1
Revises: ce057bd5ab9e
Create Date: 2026-09-20 13:11:22.558518

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3907bacd39d1"
down_revision: str | Sequence[str] | None = "ce057bd5ab9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "webhook_deliveries",
        sa.Column("target_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "webhook_deliveries",
        sa.Column("request_body", sa.LargeBinary(), nullable=True),
    )

    op.execute(
        """
        UPDATE webhook_deliveries AS delivery
        SET target_url = subscription.url,
            request_body = convert_to(delivery.payload::text, 'UTF8')
        FROM webhook_subscriptions AS subscription
        WHERE subscription.id = delivery.subscription_id
        """
    )

    op.alter_column("webhook_deliveries", "target_url", nullable=False)
    op.alter_column("webhook_deliveries", "request_body", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("webhook_deliveries", "request_body")
    op.drop_column("webhook_deliveries", "target_url")
