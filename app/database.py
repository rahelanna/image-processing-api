import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from collections.abc import Generator


load_dotenv()


database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(database_url)
SessionLocal = sessionmaker(bind=engine)

def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session