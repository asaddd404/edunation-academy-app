from pydantic import BaseModel, ConfigDict, model_validator


class ChoiceIn(BaseModel):
    text: str
    is_correct: bool = False


class QuestionIn(BaseModel):
    text: str
    choices: list[ChoiceIn]

    @model_validator(mode="after")
    def _validate_choices(self) -> "QuestionIn":
        if not (2 <= len(self.choices) <= 6):
            raise ValueError("Вопрос должен содержать от 2 до 6 вариантов ответа")
        correct_count = sum(1 for c in self.choices if c.is_correct)
        if correct_count != 1:
            raise ValueError("Ровно один вариант ответа должен быть правильным")
        return self


class ChoiceTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    is_correct: bool
    order_index: int


class QuestionTeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lesson_id: int
    text: str
    order_index: int
    choices: list[ChoiceTeacherOut]
