from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from db.models import Base


def get_engine(db_url: str | None = None):
    from config import SQLITE_DB_PATH
    url = db_url or f"sqlite:///{SQLITE_DB_PATH}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False)
