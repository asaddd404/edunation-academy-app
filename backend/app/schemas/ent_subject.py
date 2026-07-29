from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EntSubjectIn(BaseModel):
    name: str
    slug: str | None = None


class EntSubjectUpdateIn(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class EntSubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    question_count: int = 0
