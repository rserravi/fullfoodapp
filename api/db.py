from typing import Iterator
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from .config import settings

engine = create_engine(settings.db_url, echo=False)

def _column_exists(conn, table: str, column: str) -> bool:
    res = conn.execute(text(f"PRAGMA table_info('{table}')"))
    for row in res.fetchall():
        if row[1] == column:
            return True
    return False

def _safe_add_column(conn, table: str, column: str, decl: str):
    if not _column_exists(conn, table, column):
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))
        try:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table}({column})"))
        except Exception:
            pass

def migrate_user_id_columns():
    with engine.begin() as conn:
        for table in ("shoppingitem", "appliance", "planentry"):
            _safe_add_column(conn, table, "user_id", "TEXT DEFAULT 'default'")
        # columnas ya existen en ShoppingItem, pero por si vienes de una versión muy vieja:
        try:
            _safe_add_column(conn, "shoppingitem", "qty", "REAL")
            _safe_add_column(conn, "shoppingitem", "unit", "TEXT")
            _safe_add_column(conn, "shoppingitem", "category", "TEXT")
        except Exception:
            pass

def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    migrate_user_id_columns()

def get_session() -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session
