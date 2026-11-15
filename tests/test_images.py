from io import BytesIO
from typing import BinaryIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
import app.api.images as images_module


client = TestClient(app)

@pytest.mark.parametrize(
    "file_name, mime_type",
    [
        ("example.txt", "text/plain"),
        ("document.pdf", "application/pdf"),
    ],

)
def test_upload_unsupported_file_type(file_name: str, mime_type: str) -> None:
    response = client.post(
        "/images",
        files={"file": (file_name, b"Hello world", mime_type)},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported file type"}


def test_upload_invalid_image() -> None:
    response = client.post(
        "/images",
        files={"file": ("fake.jpg", b"Hello world", "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid image file"}


def test_upload_valid_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )

    assert response.status_code == 201
    payload = response.json()
    stored_file = tmp_path / payload["stored_filename"]
    assert payload["original_filename"] == "test.png"
    assert payload["stored_filename"].endswith(".png")
    assert payload["metadata"]["width"] == 10
    assert payload["metadata"]["height"] == 10
    assert payload["metadata"]["format"] == "PNG"
    assert stored_file.exists()
    assert "image_id" in payload
    assert payload["metadata"]["file_size"] > 0





def test_upload_metadata_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_metadata(image_path: Path) -> dict:
        raise ValueError("Simulated metadata failure")
    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(images_module, "extract_metadata", failing_metadata)

    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    response = client.post(
        "/images",
        files= {"file": ("test.png", buffer.getvalue(), "image/png")},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload == {"detail": "Failed to extract image metadata"}
    assert list(tmp_path.iterdir()) == []


def test_upload_storage_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_mkdir = Path.mkdir
    def failing_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self == tmp_path:
            raise PermissionError("Simulated mkdir permission denied")
        original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 500
    payload = response.json()
    assert payload == {"detail": "Failed to save image"}
    assert list(tmp_path.iterdir()) == []


def test_upload_partial_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_copyfileobj(
            source: BinaryIO,
            destination: BinaryIO,
            length: int = 0,
    ) -> None:
        destination.write(b"partial data")
        raise OSError("Simulated disk write failure")

    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(images_module.shutil, "copyfileobj", failing_copyfileobj)
    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 500
    payload = response.json()
    assert payload == {"detail": "Failed to save image"}
    assert list(tmp_path.iterdir()) == []