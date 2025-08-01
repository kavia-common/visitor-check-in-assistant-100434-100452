"""
Database connection/session configuration for FastAPI app.
Uses SQLAlchemy with PostgreSQL.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import URL

from dotenv import load_dotenv

load_dotenv()

# PUBLIC_INTERFACE
def get_postgres_url():
    """
    Constructs PostgreSQL connection string from environment variables.
    Requires:
        - POSTGRES_USER
        - POSTGRES_PASSWORD
        - POSTGRES_DB
        - POSTGRES_HOST
        - POSTGRES_PORT
    """
    return str(
        URL.create(
            drivername="postgresql+psycopg2",
            username=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", 5432),
            database=os.getenv("POSTGRES_DB"),
        )
    )

SQLALCHEMY_DATABASE_URL = get_postgres_url()

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# PUBLIC_INTERFACE
def get_db():
    """
    Yields a new database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
