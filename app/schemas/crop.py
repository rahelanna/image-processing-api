from pydantic import BaseModel, Field

class CropRequest(BaseModel):
    top: int = Field(ge=0)
    left: int = Field(ge=0)
    width: int = Field(ge=1, le=8000)
    height: int = Field(ge=1, le=8000)