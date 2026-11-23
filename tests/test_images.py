from io import BytesIO
from typing import BinaryIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from uuid import UUID

from app.main import app
import app.api.images as images_module
from app.models import processed_image
from app.models.image import Image as ImageModel
from app.models.processed_image import ProcessedImage


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


def test_upload_valid_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_database: Engine) -> None:
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

    with Session(test_database) as session:
        stored_image = session.get(ImageModel, UUID(payload["image_id"]))

        assert stored_image is not None
        assert stored_image.original_filename == "test.png"
        assert stored_image.width == 10
        assert stored_image.height == 10


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


def test_upload_database_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_commit(self: Session) -> None:
        raise SQLAlchemyError("Simulated database failure")
    monkeypatch.setattr(Session, "commit", failing_commit)
    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload == {"detail": "Failed to save image record"}
    assert list(tmp_path.iterdir()) == []


def test_get_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    post_response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    assert post_response.status_code == 201

    get_response = client.get("/images")
    assert get_response.status_code == 200
    images = get_response.json()
    assert len(images) == 1
    assert images[0]["original_filename"] == "test.png"
    assert images[0]["width"] == 10
    assert images[0]["height"] == 10
    assert images[0]["id"] == post_response.json()["image_id"]


def test_get_image_by_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    image = Image.new("RGB", (10, 10), color="red")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    post_response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    image_id = post_response.json()["image_id"]
    assert post_response.status_code == 201


    get_response = client.get(f"/images/{image_id}")
    assert get_response.status_code == 200
    image_data = get_response.json()
    assert image_data["id"] == image_id
    assert image_data["original_filename"] == "test.png"
    assert image_data["width"] == 10
    assert image_data["height"] == 10


def test_get_image_not_found() -> None:
    response = client.get("/images/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404
    assert response.json() == {"detail": "Image not found"}


def test_get_invalid_uuid() -> None:
    response = client.get("/images/456")
    assert response.status_code == 422
    assert "detail" in response.json()


def test_delete_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_database: Engine
) -> None:
    originals_dir = tmp_path / "originals"
    processed_dir = tmp_path / "processed"
    monkeypatch.setattr(images_module, "STORAGE_DIR", originals_dir)
    monkeypatch.setattr(images_module, "PROCESSED_DIR", processed_dir)

    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    post_response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )

    assert post_response.status_code == 201
    image_data = post_response.json()
    image_id = image_data["image_id"]
    stored_file = originals_dir / image_data["stored_filename"]
    assert stored_file.exists()

    resize_response_0 = client.post(
        f"/images/{image_id}/resize",
        json={"width": 50, "height": 50},
    )
    assert resize_response_0.status_code == 201
    resized_image_0 = processed_dir / resize_response_0.json()["stored_filename"]
    assert resized_image_0.exists()

    resized_respond_1 = client.post(
        f"/images/{image_id}/resize",
        json={"width": 25, "height": 25},
    )
    assert resized_respond_1.status_code == 201
    resized_image_1 = processed_dir / resized_respond_1.json()["stored_filename"]
    assert resized_image_1.exists()

    resized_id_0 = resize_response_0.json()["id"]
    resized_id_1 = resized_respond_1.json()["id"]

    delete_response = client.delete(f"/images/{image_id}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert list(originals_dir.iterdir()) == []
    assert list(processed_dir.iterdir()) == []

    get_response = client.get(f"/images/{image_id}")
    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "Image not found"}

    with Session(test_database) as session:
        assert session.get(ProcessedImage, UUID(resized_id_0)) is None
        assert session.get(ProcessedImage, UUID(resized_id_1)) is None


def test_delete_image_without_processed_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    post_response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    assert post_response.status_code == 201
    image_id = post_response.json()["image_id"]
    delete_response = client.delete(f"/images/{image_id}")
    assert delete_response.status_code == 204
    assert list(tmp_path.iterdir()) == []
    get_response = client.get(f"/images/{image_id}")
    assert get_response.status_code == 404
    assert delete_response.content == b""


def test_delete_image_not_found() -> None:
    response = client.delete("/images/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404
    assert response.json() == {"detail": "Image not found"}


def test_delete_image_database_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(images_module, "STORAGE_DIR", tmp_path)
    image = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    post_response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    image_data = post_response.json()
    image_id = image_data["image_id"]
    stored_file = tmp_path / image_data["stored_filename"]

    assert stored_file.exists()

    def failing_commit(self: Session) -> None:
        raise SQLAlchemyError("Simulated database failure")

    monkeypatch.setattr(Session, "commit", failing_commit)
    response = client.delete(f"/images/{image_id}")
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to delete image record"}
    assert stored_file.exists()
    assert list(tmp_path.iterdir()) == [stored_file]

    get_response = client.get(f"/images/{image_id}")
    assert get_response.status_code == 200


@pytest.mark.parametrize(
    "operation, payload",
    [
        ("resize", {"width": 50, "height": 30}),
        ("rotate", {"angle": 90}),
    ]
)
def test_process_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_database: Engine,
    operation: str,
    payload: dict[str, int],
) -> None:
    originals_dir = tmp_path / "originals"
    processed_dir = tmp_path / "processed"
    monkeypatch.setattr(images_module, "STORAGE_DIR", originals_dir)
    monkeypatch.setattr(images_module, "PROCESSED_DIR", processed_dir)

    image = Image.new("RGB", (100, 60), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    post_response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    assert post_response.status_code == 201
    source_image_id = post_response.json()["image_id"]
    stored_filename = post_response.json()["stored_filename"]
    original_file = originals_dir / stored_filename

    processed_response = client.post(
        f"/images/{source_image_id}/{operation}",
        json=payload,
    )
    assert processed_response.status_code == 201
    processed_data = processed_response.json()
    processed_image_id = processed_data["id"]

    processed_file = processed_dir / processed_data["stored_filename"]

    assert processed_file.exists()

    with Image.open(processed_file) as processed_image:
        if operation == "resize":
            assert processed_image.size == (50, 30)
        elif operation == "rotate":
            assert processed_image.size == (60, 100)

    assert processed_data["source_image_id"] == source_image_id

    with Session(test_database) as session:
        processed_record = session.get(ProcessedImage, UUID(processed_image_id))

        assert processed_record is not None
        assert processed_record.source_image_id == UUID(source_image_id)
        if operation == "resize":
            assert processed_record.width == 50
            assert processed_record.height == 30
        elif operation == "rotate":
            assert processed_record.width == 60
            assert processed_record.height == 100

    assert original_file.exists()

    with Image.open(original_file) as original_image:
        assert original_image.size == (100, 60)

@pytest.mark.parametrize(
    "operation, payload",
    [
        ("resize", {"width": 50, "height": 30}),
        ("rotate", {"angle": 90}),
    ]
)
def test_processing_image_not_found(operation:str, payload: dict[str, int]) -> None:
    response = client.post(
        f"/images/00000000-0000-4000-8000-000000000000/{operation}",
        json=payload

    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Image not found"}


@pytest.mark.parametrize(
    "width, height",
    [
        (0, 100),
        (100, -5),
        (8001, 100),
        (100, 8001),
    ],
)
def test_resize_image_invalid_dimensions(width: int, height: int) -> None:
    post_response = client.post(
        "/images/00000000-0000-4000-8000-000000000000/resize",
        json= {"width": width, "height": height}
    )
    assert post_response.status_code == 422
    assert "detail" in post_response.json()


def test_rotate_image_invalid_angle() -> None:
    post_response = client.post(
        "/images/00000000-0000-4000-8000-000000000000/rotate",
        json= {"angle": -90}
    )
    assert post_response.status_code == 422
    assert "detail" in post_response.json()


@pytest.mark.parametrize(
    "operation, payload",
    [
        ("resize", {"width": 50, "height": 30}),
        ("rotate", {"angle": 90}),
    ]
)
def test_process_image_database_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    payload: dict[str, int],
) -> None:
    originals_dir = tmp_path / "originals"
    processed_dir = tmp_path / "processed"
    monkeypatch.setattr(images_module, "STORAGE_DIR", originals_dir)
    monkeypatch.setattr(images_module, "PROCESSED_DIR", processed_dir)

    image = Image.new("RGB", (100, 100), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    post_response = client.post(
        "/images",
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    assert post_response.status_code == 201
    image_id = post_response.json()["image_id"]
    stored_file = originals_dir / post_response.json()["stored_filename"]

    def failing_commit(self: Session) -> None:
        raise SQLAlchemyError("Simulated database failure")
    monkeypatch.setattr(Session, "commit", failing_commit)

    resized_response = client.post(
        f"/images/{image_id}/{operation}",
        json=payload,
    )
    assert resized_response.status_code == 500
    assert resized_response.json() == {"detail": "Failed to save processed image record"}
    assert list(processed_dir.iterdir()) == []
    assert stored_file.exists()
