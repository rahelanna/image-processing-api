from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ImageResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    width: int
    height: int
    format: str
    file_size: int
    created_at: datetime


class ProcessedImageResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_image_id: UUID
    stored_filename: str
    width: int
    height: int
    format: str
    file_size: int
    created_at: datetime