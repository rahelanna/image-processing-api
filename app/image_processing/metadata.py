from pathlib import Path
from datetime import datetime

from PIL import Image, ExifTags


def normalize_exif_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip("\x00").strip()

    return normalized or None

def parse_exif_datetime(value: object) -> datetime | None:
    value = normalize_exif_text(value)
    if not isinstance(value, str):
        return None

    try:
        normalized_datetime = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return normalized_datetime


def extract_metadata(image_path: Path) -> dict:
    with Image.open(image_path) as img:
        width, height = img.size
        image_format = img.format
        exif = img.getexif()
        exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    date_time_original = exif_ifd.get(36867)
    date_time_original = parse_exif_datetime(date_time_original)

    camera_make = None
    camera_model = None
    date_time = None
    orientation = None
    software = None

    for tag_id, tag_value in exif.items():
        tag_name = ExifTags.TAGS.get(tag_id, tag_id)

        if tag_name == "Make":
            camera_make = normalize_exif_text(tag_value)
        if tag_name == "Model":
            camera_model = normalize_exif_text(tag_value)
        if tag_name == "DateTime":
            date_time = parse_exif_datetime(tag_value)
        if tag_name == "Orientation":
            orientation = tag_value
        if tag_name == "Software":
            software = normalize_exif_text(tag_value)

    metadata = {
        "camera_make": camera_make,
        "camera_model": camera_model,
        "date_time": date_time,
        "captured_at": date_time_original,
        "orientation": orientation,
        "software": software,
    }

    file_size = image_path.stat().st_size
    return {
        "width": width,
        "height": height,
        "format": image_format,
        "file_size": file_size,
        **metadata
    }