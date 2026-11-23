from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID

class RotateRequest(BaseModel):
    angle: Literal[90, 180, 270]