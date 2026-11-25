from pathlib import Path
from urllib import request
from uuid import uuid4, UUID
import shutil
import logging

from fastapi import APIRouter, HTTPException, File, UploadFile, status, Depends
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from app.image_processing.metadata import extract_metadata
from app.database import get_db
from app.models.image import Image as ImageModel
from app.schemas.crop import CropRequest
from app.schemas.image import ImageResponse, ProcessedImageResponse
from app.schemas.resize import ResizeRequest
from app.image_processing.resize import resize_image
from app.models.processed_image import ProcessedImage
from app.schemas.rotate import RotateRequest
from app.image_processing.rotate import rotate_image
from app.image_processing.grayscale import grayscale_image
from app.image_processing.crop import crop_image
from app.services.image_processing import process_image, cleanup_file

images_router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 25 * 1024 * 1024
STORAGE_DIR = Path("storage/originals")
PROCESSED_DIR = Path("storage/processed")


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
        "id": image_id,
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


@images_router.delete(
    "/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_image(image_id: UUID, db: Session = Depends(get_db)):
    image = db.get(ImageModel, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    storage_path = STORAGE_DIR / image.stored_filename

    statement = select(ProcessedImage).where(
        ProcessedImage.source_image_id == image_id
    )
    processed_images = db.scalars(statement).all()

    processed_paths = [
        PROCESSED_DIR / processed_image.stored_filename
        for processed_image in processed_images
    ]

    all_paths = [storage_path, *processed_paths]

    file_pairs = [
        (path, path.with_name(path.name + ".deleting"))
        for path in all_paths
    ]

    renamed_files: list[tuple[Path, Path]] = []

    try:
        for original_path, temporary_path in file_pairs:
            original_path.rename(temporary_path)
            renamed_files.append((original_path, temporary_path))

    except OSError:
        logger.exception("Failed to prepare image deletion: %s", image_id)

        for original_path, temporary_path in reversed(renamed_files):
            try:
                temporary_path.rename(original_path)
            except OSError:
                logger.exception("Failed to restore image file: %s", temporary_path)

        raise HTTPException(
            status_code=500,
            detail="Failed to prepare image deletion",
        )

    try:
        for processed_image in processed_images:
            db.delete(processed_image)
        db.delete(image)
        db.commit()
    except SQLAlchemyError:
        logger.exception("Failed to delete image record: %s", image_id)
        db.rollback()
        for original_path, temporary_path in reversed(renamed_files):
            try:
                temporary_path.rename(original_path)
            except OSError:
                logger.exception("Failed to restore image file: %s", temporary_path)
        raise HTTPException(status_code=500, detail="Failed to delete image record")

    for _, temporary_path in renamed_files:
        cleanup_file(temporary_path)


@images_router.post("/images/{image_id}/resize", response_model=ProcessedImageResponse, status_code=status.HTTP_201_CREATED)
def resize_image_endpoint(image_id: UUID, request: ResizeRequest, db: Session = Depends(get_db)):

    return process_image(
        image_id, db,
        STORAGE_DIR,
        PROCESSED_DIR,
        operation=lambda source, output: resize_image(
            source,
            output,
            request.width,
            request.height,
        )
    )


@images_router.post(
    "/images/{image_id}/rotate", status_code=status.HTTP_201_CREATED, response_model=ProcessedImageResponse)
def rotate_image_endpoint(image_id: UUID, request: RotateRequest, db: Session = Depends(get_db)):

    return process_image(
        image_id,
        db,
        STORAGE_DIR,
        PROCESSED_DIR,
        operation=lambda source, output: rotate_image(
            source,
            output,
            request.angle,
        )
    )


@images_router.post(
    "/images/{image_id}/grayscale", response_model=ProcessedImageResponse, status_code=status.HTTP_201_CREATED
)
def grayscale_image_endpoint(image_id: UUID, db: Session = Depends(get_db)):

    return process_image(
        image_id,
        db,
        STORAGE_DIR,
        PROCESSED_DIR,
        grayscale_image,
    )


@images_router.post(
    "/images/{image_id}/crop", response_model=ProcessedImageResponse, status_code=status.HTTP_201_CREATED
)
def crop_image_endpoint(image_id: UUID, request: CropRequest, db: Session = Depends(get_db)):

    return process_image(
        image_id,
        db,
        STORAGE_DIR,
        PROCESSED_DIR,
        operation=lambda source, output: crop_image(
            source,
            output,
            request.top,
            request.left,
            request.width,
            request.height,
        )
    )


@images_router.get(
    "/images/processed/{processed_id}/download", status_code=status.HTTP_200_OK
)
def download_processed_image_endpoint(processed_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    image = db.get(ProcessedImage, processed_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Processed image not found")

    file_path = PROCESSED_DIR / image.stored_filename

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Processed image file not found")

    return FileResponse(path=file_path, media_type=f"image/{image.format.lower()}")

@images_router.get(
    "/images/{image_id}/download", status_code=status.HTTP_200_OK
)
def download_original_image_endpoint(image_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    image = db.get(ImageModel, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = STORAGE_DIR / image.stored_filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Original image file not found")
    return FileResponse(path=file_path, media_type=f"image/{image.format.lower()}")