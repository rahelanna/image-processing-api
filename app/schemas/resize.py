from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID


class ResizeRequest(BaseModel):
    width: int = Field(ge=1, le=8000)
    height: int = Field(ge=1, le=8000)

class ResizeResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_image_id: UUID
    stored_filename: str
    width: int
    height: int
    format: str
    file_size: int
    created_at: datetime