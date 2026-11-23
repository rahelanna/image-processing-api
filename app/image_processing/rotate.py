from pathlib import Path

from PIL import Image

def rotate_image(image_path: Path, output_path: Path, angle: int) -> tuple[int, int]:
    with Image.open(image_path) as image:
        image_format = image.format
        rotated_image = image.rotate(angle, expand=True)

    rotated_image.save(output_path, format=image_format)

    return rotated_image.size