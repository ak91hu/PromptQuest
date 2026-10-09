"""Request types and input size limits."""

from pydantic import BaseModel, Field


class StationAction(BaseModel):
    # Existing API clients may omit this; browser actions bind to their displayed station.
    station: int | None = Field(default=None, ge=0, le=14)


class Start(BaseModel):
    team: str = Field(default="Operator", max_length=40)


class Chat(StationAction):
    message: str = Field(default="", max_length=2500)
    document: str = Field(default="", max_length=5000)


class Code(StationAction):
    code: str = Field(max_length=250)


class Hint(StationAction):
    token: str = Field(default="", max_length=64)


class Note(StationAction):
    note: str = Field(max_length=2000)


class Defense(BaseModel):
    choices: list[str] = Field(max_length=5)
