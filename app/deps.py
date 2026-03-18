from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, create_engine

from app.core.config import settings


connect_args = {"check_same_thread": False} if settings.sqlite_url.startswith("sqlite") else {}
engine = create_engine(settings.sqlite_url, echo=False, connect_args=connect_args)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

