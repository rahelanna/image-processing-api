from pathlib import Path

from PIL import Image

def grayscale_image(image_path: Path, output_path: Path) -> None:
    with Image.open(image_path) as image:
        image_format = image.format
        grayscaled_image = image.convert("L")

    grayscaled_image.save(output_path, format=image_format)