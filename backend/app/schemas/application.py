from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.application import ApplicationStatusEnum


class ApplicationCreateIn(BaseModel):
    category_id: int


class ApplicationOut(BaseModel):
    # Deliberately flat: no nested student/category ORM objects here. Reading
    # an unloaded relationship attribute on an AsyncSession object outside of
    # an awaited context raises SQLAlchemy's MissingGreenlet error, so the
    # display-only name fields below are filled in explicitly by the route
    # handler only when it has eager-loaded the relationship (selectinload),
    # never via automatic attribute access.
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    category_id: int
    status: ApplicationStatusEnum
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime
    student_name: str | None = None
    student_phone: str | None = None
    category_name: str | None = None
