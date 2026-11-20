from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Id = Annotated[int, Field(gt=0, le=2_147_483_647)]


class Payload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ModelEdit(Payload):
    model: str = Field(min_length=3, max_length=160, pattern=r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_./:@-]+$")
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(ge=64, le=8192)


class ModelView(ModelEdit):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str


class Title(Payload):
    title: str = Field(min_length=1, max_length=120)


class ChatInput(Payload):
    model_id: Id
    message: str = Field(min_length=1, max_length=4000)
    mode: Literal["chat", "rag"] = "chat"


class AgentInput(Payload):
    model_id: Id
    prompt: str = Field(min_length=1, max_length=4000)
