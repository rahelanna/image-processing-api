from pathlib import Path
from PIL import Image


def crop_image(
        image_path: Path,
        output_path: Path,
        top: int,
        left: int,
        width: int,
        height: int,
) -> None:
    with Image.open(image_path) as image:
        image_format = image.format

        if left + width > image.width or top + height > image.height:
            raise ValueError("Crop area exceeds image boundaries")

        cropped_image = image.crop((left, top, left + width, top + height))

    cropped_image.save(output_path, format=image_format)
