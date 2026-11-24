from pathlib import Path

from PIL import Image


def resize_image(image_path: Path, output_path: Path, width: int, height: int) -> tuple[int, int]:
    with Image.open(image_path) as image:
        image_format = image.format
        resized_image = image.resize((width, height), resample= Image.Resampling.LANCZOS,)

    resized_image.save(output_path, format=image_format)

    return resized_image.size



