from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import APIRouter, HTTPException, File, UploadFile, status
from PIL import Image

from app.image_processing.metadata import extract_metadata


images_router = APIRouter()
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

@images_router.post("/images", status_code=status.HTTP_201_CREATED)
def upload_image(file: UploadFile = File(...)):
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
        metadata = extract_metadata(storage_path)
    except OSError:
        if file_created:
            try:
                storage_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save image")

    return {
        "image_id": image_id,
        "original_filename": file.filename,
        "stored_filename": stored_filename,
        "metadata": metadata,
    }