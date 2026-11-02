# Image Processing API

A RESTful API for image processing, built with Python and FastAPI.

The API provides a backend solution for uploading, processing, and managing images. It is designed for photography workflows, e-commerce applications, and software projects that require automated image optimization and transformation.

All image operations follow a **non-destructive approach**, preserving the original files while storing processed versions separately.

## Features

- **Image Compression:** Optimize image file sizes with configurable quality settings.
- **Format Conversion:** Convert images between JPEG, PNG, WebP, and other supported formats.
- **Metadata Extraction:** Extract image dimensions, format, file size, and available EXIF metadata.
- **Image Transformations:** Resize, crop, rotate, sharpen, blur, and adjust image properties.
- **Image Management:** Upload, retrieve, list, and delete images through REST API endpoints.
- **Image Variants:** Manage processed versions without modifying the original images.

## Tech Stack

- **Python** - Core programming language
- **FastAPI** - REST API framework
- **Pillow** - Image processing and metadata extraction
- **OpenCV** - Advanced image processing
- **PostgreSQL** - Relational database
- **SQLAlchemy** - Database ORM
- **Pydantic** - Data validation
- **pytest** - Automated testing
- **Docker** - Containerization

