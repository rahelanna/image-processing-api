from pathlib import Path
from uuid import uuid4, UUID
import shutil
import logging

from fastapi import APIRouter, HTTPException, File, UploadFile, status, Depends
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from app.image_processing.metadata import extract_metadata
from app.database import get_db
from app.models.image import Image as ImageModel
from app.schemas.image import ImageResponse


images_router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 25 * 1024 * 1024
STORAGE_DIR = Path("storage/originals")


allowed_formats = {
    "image/jpeg" :  "JPEG",
    "image/png" : "PNG",
    "image/webp" : "WEBP",
}

EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}

def cleanup_file(file_path: Path) -> None:
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Failed to delete file: %s", file_path)

@images_router.post("/images", status_code=status.HTTP_201_CREATED)
def upload_image(
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
):

    if file.content_type not in allowed_formats:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="File size exceeds 25 MiB limit")

    try:
        with Image.open(file.file) as image:
            if image.format != allowed_formats[file.content_type]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image format does not match MIME type")
            image.verify()
        file.file.seek(0)
        with Image.open(file.file) as image:
            image.load()
            image_format = image.format
    except OSError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image file")
    file.file.seek(0)

    image_id = str(uuid4())
    extension = EXTENSIONS[image_format]
    stored_filename = f"{image_id}{extension}"
    storage_path = STORAGE_DIR / stored_filename

    file_created = False

    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        with storage_path.open(mode="xb") as destination:
            file_created = True
            shutil.copyfileobj(file.file, destination, length=1024*1024)
    except OSError:
        logger.exception("Failed to save image: %s", storage_path)
        if file_created:
            cleanup_file(storage_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save image")

    try:
        metadata = extract_metadata(storage_path)
        image_record = ImageModel(
            id=UUID(image_id),
            original_filename=file.filename,
            stored_filename=stored_filename,
            width=metadata["width"],
            height=metadata["height"],
            format=metadata["format"],
            file_size=metadata["file_size"],
            captured_at=metadata["captured_at"],
            camera_make=metadata["camera_make"],
            camera_model=metadata["camera_model"],
            software=metadata["software"],
            orientation=metadata["orientation"],
        )
    except Exception:
        logger.exception("Failed to extract metadata: %s", storage_path)
        cleanup_file(storage_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract image metadata")
    try:
        db.add(image_record)
        db.commit()
    except SQLAlchemyError:
        logger.exception("Failed to save image record: %s", storage_path)
        db.rollback()
        cleanup_file(storage_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save image record")
    return {
        "image_id": image_id,
        "original_filename": file.filename,
        "stored_filename": stored_filename,
        "metadata": metadata,
    }


@images_router.get("/images", response_model=list[ImageResponse])
def get_images(db: Session = Depends(get_db)):
    statement = select(ImageModel)

    return db.scalars(statement).all()


@images_router.get("/images/{image_id}", response_model=ImageResponse)
def get_image(image_id: UUID, db: Session = Depends(get_db)):
    image = db.get(ImageModel, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image