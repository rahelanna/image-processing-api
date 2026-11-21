from app.models.base import Base
from uuid import UUID, uuid4

from sqlalchemy import String, ForeignKey, Integer, BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

class ProcessedImage(Base):
    __tablename__ = 'processed_images'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_image_id: Mapped[UUID] = mapped_column(ForeignKey('images.id'), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
