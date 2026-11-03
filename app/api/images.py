from fastapi import APIRouter, HTTPException, File, UploadFile, status
from PIL import Image

images_router = APIRouter()
MAX_FILE_SIZE = 25 * 1024 * 1024


allowed_formats = {
    "image/jpeg" :  "JPEG",
    "image/png" : "PNG",
    "image/webp" : "WEBP",
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
    except OSError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image file")
    file.file.seek(0)
    return {"filename": file.filename}