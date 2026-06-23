# __init__.py (db/)

## Summary
Database engine factory for FitAi. Provides `get_engine()` which creates a SQLAlchemy engine with WAL mode set via a connect event listener, and calls `create_all` to initialize schema. Also provides `get_session_factory()` for creating sessionmaker instances. Used by the main app and Prefect flows; tests use their own StaticPool engine directly to avoid importing config.

## Functions
- get_engine(db_url=None) → Engine — creates SQLAlchemy engine; imports SQLITE_DB_PATH from config if db_url not provided; sets WAL pragma on connect; calls Base.metadata.create_all
- get_session_factory(engine) → sessionmaker — returns configured sessionmaker bound to engine

## Non-function code
- Imports Base from db.models for create_all

## Imports
- sqlalchemy — create_engine, event
- sqlalchemy.orm — sessionmaker, Session
- db.models — Base

## Imported by
- Main bot entrypoint (future)
- Prefect flows (future)

## Tags
database, config, sqlalchemy, engine

## Node path
db/__init__.py
