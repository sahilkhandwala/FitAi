# __init__.py (db/)

## Summary
Database factory module. Provides get_engine() to create a SQLAlchemy engine with WAL mode and auto-creates all tables, and get_session_factory() to return a sessionmaker. Imports Base from db/models.py to trigger table creation.

## Functions
- get_engine(db_url=None) — creates SQLAlchemy engine; defaults to SQLITE_DB_PATH from config; sets WAL pragma via event listener; calls Base.metadata.create_all
- get_session_factory(engine) — returns a sessionmaker bound to the given engine

## Non-function code
(none beyond function definitions)

## Imports
- sqlalchemy — create_engine, event
- sqlalchemy.orm — sessionmaker, Session
- db.models — Base

## Imported by
- bot/main.py — get_engine, get_session_factory

## Tags
database, sqlalchemy, sqlite, factory

## Node path
db/__init__.py
