
from uuid import UUID, uuid4
from pathlib import Path

import logging
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from collections.abc import Callable
from app.models.processed_image import ProcessedImage
from app.models.image import Image as ImageModel


logger = logging.getLogger(__name__)

def cleanup_file(file_path: Path) -> None:
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Failed to delete file: %s", file_path)


def process_image(image_id: UUID, db: Session, storage_dir: Path, processed_dir: Path, operation: Callable[[Path, Path], tuple[int, int]]) -> ProcessedImage:
    image = db.get(ImageModel, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    source_path = storage_dir / image.stored_filename
    extension = source_path.suffix
    processed_id = str(uuid4())
    output_path = processed_dir / f"{processed_id}{extension}"

    try:
        processed_dir.mkdir(parents=True, exist_ok=True)
        width, height = operation(source_path, output_path)
        processed_file_size = output_path.stat().st_size
    except OSError as exc:
        logger.exception("Failed to save processed image record %s", output_path)
        cleanup_file(output_path)
        raise HTTPException(status_code=500, detail="Failed to save processed image record") from exc
    except ValueError as exc:
        cleanup_file(output_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    processed_image = ProcessedImage(
        id=UUID(processed_id),
        source_image_id=image_id,
        stored_filename=output_path.name,
        width=width,
        height=height,
        format=image.format,
        file_size=processed_file_size,
    )

    try:
        db.add(processed_image)
        db.commit()
    except SQLAlchemyError as exc:
        logger.exception("Failed to save processed image record %s", output_path)
        db.rollback()
        cleanup_file(output_path)
        raise HTTPException(status_code=500, detail="Failed to save processed image record") from exc

    return processed_image