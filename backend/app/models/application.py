import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApplicationStatusEnum(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[ApplicationStatusEnum] = mapped_column(
        Enum(ApplicationStatusEnum, name="application_status_enum", native_enum=True),
        default=ApplicationStatusEnum.pending,
        nullable=False,
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["User"] = relationship(foreign_keys=[student_id])
    category: Mapped["Category"] = relationship()
    decider: Mapped["User | None"] = relationship(foreign_keys=[decided_by])

    __table_args__ = (
        # Only one *pending* application per (student, category) at a time —
        # a plain unique constraint would block reapplying after a rejection.
        Index(
            "uq_pending_application_per_student_category",
            "student_id",
            "category_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
