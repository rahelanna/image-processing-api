from pydantic import BaseModel, Field


class ResizeRequest(BaseModel):
    width: int = Field(ge=1, le=8000)
    height: int = Field(ge=1, le=8000)
