from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.data.models.batch import Batch


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index(
            "idx_product_batch_aggregated",
            "batch_id",
            "is_aggregated",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    unique_code: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id"),
        nullable=False,
        index=True,
    )
    is_aggregated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    aggregated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    batch: Mapped[Batch] = relationship(back_populates="products")
