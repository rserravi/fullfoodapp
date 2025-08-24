from typing import Iterator
from sqlmodel import SQLModel, create_engine, Session
from .config import settings

engine = create_engine(settings.db_url, echo=False)

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

def get_session() -> Iterator[Session]:
    # Desactiva la expiración de atributos tras commit (evita {} en respuestas)
    with Session(engine, expire_on_commit=False) as session:
        yield session
