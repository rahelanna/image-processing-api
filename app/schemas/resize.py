from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID


class ResizeRequest(BaseModel):
    width: int = Field(ge=1, le=8000)
    height: int = Field(ge=1, le=8000)
